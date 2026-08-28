"""S3 兼容文档存储的无网络确定性测试。"""

from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from app.storage import DocumentStorageError
from app.storage.s3 import S3DocumentStorage


class FakeS3Error(Exception):
    """只提供生产实现用于识别错误的 S3 code。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class FakeObjectResponse:
    """模拟 MinIO get_object 返回的 urllib3 流式响应。"""

    def __init__(self, content: bytes) -> None:
        self.stream = BytesIO(content)
        self.closed = False
        self.released = False

    def read(self, size: int) -> bytes:
        return self.stream.read(size)

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class FakeMinioClient:
    """记录 SDK 调用并把对象内容保存在测试进程内存中。"""

    def __init__(self, *, bucket_exists: bool = False) -> None:
        self.has_bucket = bucket_exists
        self.objects: dict[str, bytes] = {}
        self.downloads: list[tuple[str, str, str]] = []
        self.last_response: FakeObjectResponse | None = None

    def bucket_exists(self, bucket: str) -> bool:
        del bucket
        return self.has_bucket

    def make_bucket(self, bucket: str, **_: object) -> None:
        del bucket
        self.has_bucket = True

    def stat_object(self, bucket: str, object_key: str) -> object:
        del bucket
        if object_key not in self.objects:
            raise FakeS3Error("NoSuchKey")
        return object()

    def fput_object(self, bucket: str, object_key: str, path: str) -> None:
        del bucket, path
        self.objects[object_key] = b"stored document content"

    def fget_object(self, bucket: str, object_key: str, path: str) -> None:
        if object_key not in self.objects:
            raise FakeS3Error("NoSuchKey")
        self.downloads.append((bucket, object_key, path))

    def get_object(self, bucket: str, object_key: str) -> FakeObjectResponse:
        del bucket
        if object_key not in self.objects:
            raise FakeS3Error("NoSuchKey")
        self.last_response = FakeObjectResponse(self.objects[object_key])
        return self.last_response

    def remove_object(self, bucket: str, object_key: str) -> None:
        del bucket
        self.objects.pop(object_key, None)


async def test_s3_storage_complete_lifecycle() -> None:
    """上传、下载、流式读取和重复删除必须遵守统一存储接口。"""

    client = FakeMinioClient()
    storage = S3DocumentStorage(
        endpoint="127.0.0.1:9000",
        access_key="access-key",
        secret_key="secret-key",
        bucket="qa-documents",
        secure=False,
        auto_create_bucket=True,
        client=client,
    )
    source = Path("fake-upload.tmp")
    object_key = "project/8/document/uuid-source.pdf"

    # 假客户端不读取真实文件；这里只验证上传成功后才调用临时文件删除。
    with patch.object(Path, "unlink", autospec=True) as unlink_mock:
        await storage.save_file(source, object_key)
        unlink_mock.assert_called_once_with(source, missing_ok=True)

    assert client.has_bucket
    assert object_key in client.objects

    await storage.download_file(object_key, Path("fake-download.tmp"))
    assert client.downloads == [
        ("qa-documents", object_key, "fake-download.tmp")
    ]

    chunks = [chunk async for chunk in storage.stream_file(object_key, 7)]
    assert b"".join(chunks) == b"stored document content"
    assert client.last_response is not None
    assert client.last_response.closed
    assert client.last_response.released

    await storage.delete_file(object_key)
    await storage.delete_file(object_key)
    assert object_key not in client.objects


async def test_s3_storage_rejects_missing_object_and_unsafe_key() -> None:
    """不存在对象转换成统一异常，危险对象键在发送网络请求前被拒绝。"""

    storage = S3DocumentStorage(
        endpoint="s3.example.com",
        access_key="access-key",
        secret_key="secret-key",
        bucket="qa-documents",
        client=FakeMinioClient(bucket_exists=True),
    )

    try:
        await storage.download_file("missing.pdf", Path("unused.tmp"))
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("不存在的 S3 对象没有转换成 FileNotFoundError")

    try:
        await storage.delete_file("../../outside.txt")
    except ValueError:
        pass
    else:
        raise AssertionError("危险对象键没有被拒绝")


async def test_s3_storage_does_not_create_production_bucket_by_default() -> None:
    """未开启自动建桶时，缺失 Bucket 必须明确失败。"""

    storage = S3DocumentStorage(
        endpoint="s3.example.com",
        access_key="access-key",
        secret_key="secret-key",
        bucket="missing-bucket",
        client=FakeMinioClient(bucket_exists=False),
    )
    try:
        await storage.delete_file("safe/object.txt")
    except RuntimeError as exc:
        assert "Bucket 不存在" in str(exc)
    else:
        raise AssertionError("生产模式缺失 Bucket 时没有按预期失败")


async def test_s3_storage_converts_sdk_failure_to_retryable_io_error() -> None:
    """SDK 网络错误必须转换成 Worker 能识别并自动重试的 I/O 错误。"""

    client = FakeMinioClient(bucket_exists=True)
    storage = S3DocumentStorage(
        endpoint="s3.example.com",
        access_key="access-key",
        secret_key="secret-key",
        bucket="qa-documents",
        client=client,
    )

    with patch.object(
        client,
        "get_object",
        side_effect=ConnectionError("temporary network failure"),
    ):
        try:
            chunks = [chunk async for chunk in storage.stream_file("safe.pdf")]
            del chunks
        except DocumentStorageError as exc:
            assert isinstance(exc, OSError)
            assert "读取 S3 对象失败" in str(exc)
        else:
            raise AssertionError("SDK 网络错误没有转换成可重试存储错误")

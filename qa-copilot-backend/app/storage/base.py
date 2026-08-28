from collections.abc import AsyncIterator
from pathlib import Path, PurePosixPath
from typing import Protocol


class DocumentStorageError(OSError):
    """本地磁盘或远程对象存储发生的可重试 I/O 故障。"""


def validate_object_key(object_key: str) -> str:
    """校验本地存储和 S3 共用的对象键。

    功能：拒绝空值、绝对路径、Windows 分隔符和 ``..`` 路径穿越片段。
    作用：所有存储实现都先调用它，确保数据库中的 ``object_key`` 在本地磁盘、
    MinIO 和 Amazon S3 中表达同一个安全的相对对象名称。
    为什么用它：如果每个实现各写一套校验，切换后可能出现规则不一致；使用
    POSIX 路径格式也符合 S3 对象键通常使用正斜杠分层的约定。
    """

    if not object_key or "\\" in object_key or ":" in object_key:
        raise ValueError("非法的文档对象键")

    key_path = PurePosixPath(object_key)
    if key_path.is_absolute() or any(
        part in {"", ".", ".."} for part in key_path.parts
    ):
        raise ValueError("非法的文档对象键")
    return object_key


class DocumentStorage(Protocol):
    """知识文档对象存储协议。

    Service 只依赖这个协议，不关心底层使用本地磁盘、MinIO 还是 S3。
    后续增加生产存储实现时，只要完整实现保存、删除、下载和流式读取能力即可替换。
    """

    async def save_file(self, source_path: Path, object_key: str) -> None:
        """把临时文件保存到 object_key，并在成功后移除临时文件。"""
        ...

    async def delete_file(self, object_key: str) -> None:
        """删除对象；对象不存在时按幂等成功处理。"""
        ...

    async def download_file(self, object_key: str, destination_path: Path) -> None:
        """把对象下载到 Worker 的临时路径，供解析器读取。"""
        ...

    def stream_file(self, object_key: str, chunk_size: int = 64 * 1024) -> AsyncIterator[bytes]:
        """分块读取对象，供 HTTP StreamingResponse 持续返回文件内容。"""
        ...

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from threading import Lock
from typing import Any

from app.storage.base import DocumentStorageError, validate_object_key


def _is_not_found_error(exc: Exception) -> bool:
    """识别 MinIO/S3 SDK 返回的对象不存在错误。"""

    return getattr(exc, "code", None) in {
        "NoSuchKey",
        "NoSuchObject",
        "NoSuchBucket",
        "XMinioInvalidObjectName",
    }


class S3DocumentStorage:
    """基于 MinIO Python SDK 的 S3 兼容知识文档存储。

    功能：实现上传、下载、删除和分块读取四个 ``DocumentStorage`` 操作。
    作用：API 与 Celery Worker 通过统一工厂取得本类后，可以共享 MinIO 或
    Amazon S3 中的同一份原始文档，不依赖某台应用服务器的本地磁盘。
    为什么用它：MinIO SDK 同时支持 MinIO 和标准 S3 协议，能用一套实现覆盖
    私有化部署和云存储；SDK 是同步接口，所以阻塞网络操作通过
    ``asyncio.to_thread`` 交给线程执行，避免阻塞 FastAPI 事件循环。
    """

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = True,
        region: str | None = None,
        session_token: str | None = None,
        auto_create_bucket: bool = False,
        client: Any | None = None,
    ) -> None:
        """创建一个可复用的 S3 客户端。

        功能：接收对象存储连接信息，并延迟准备 Bucket。

        作用：由统一存储工厂在 FastAPI 或 Celery Worker 进程内创建一次，随后被
        上传、索引、下载和删除流程共同复用。

        为什么用它：MinIO Python Software Development Kit（Python 软件开发工具包）
        的客户端内部维护连接池，复用客户端比每次文件操作都重新创建连接更高效；
        Bucket 检查则延迟到第一次真正访问时执行，避免仅导入应用就访问外部服务。
        """

        if not endpoint or "://" in endpoint:
            raise ValueError("S3 endpoint 只能填写 host:port，不能包含协议前缀")
        if not bucket:
            raise ValueError("S3 bucket 不能为空")
        if not access_key:
            raise ValueError("S3 access key 不能为空")
        if not secret_key:
            raise ValueError("S3 secret key 不能为空")

        self.bucket = bucket
        self.region = region
        self.auto_create_bucket = auto_create_bucket
        self._bucket_ready = False
        self._bucket_lock = Lock()

        if client is None:
            try:
                # pyrefly: ignore [missing-import]
                from minio import Minio
            except ImportError as exc:
                raise RuntimeError(
                    "启用 S3/MinIO 存储前必须安装 storage 依赖："
                    "uv sync --extra storage"
                ) from exc
            client = Minio(
                endpoint,
                access_key=access_key,
                secret_key=secret_key,
                session_token=session_token,
                secure=secure,
                region=region,
            )
        self.client = client

    def _ensure_bucket_sync(self) -> None:
        """首次使用时检查 Bucket，并按配置决定是否自动创建。

        功能：确认对象存储容器存在。
        作用：所有读写操作的共同前置条件，只在当前进程首次访问时执行远程检查。
        为什么用它：生产 Bucket 通常由基础设施预先创建，所以默认缺失即报错；
        本地 MinIO 可开启自动创建。线程锁避免并发首请求重复创建同一 Bucket。
        """

        if self._bucket_ready:
            return
        with self._bucket_lock:
            if self._bucket_ready:
                return
            try:
                bucket_exists = self.client.bucket_exists(self.bucket)
            except Exception as exc:
                raise DocumentStorageError("检查 S3 Bucket 失败") from exc
            if not bucket_exists:
                if not self.auto_create_bucket:
                    raise RuntimeError(f"S3 Bucket 不存在：{self.bucket}")
                kwargs = {"location": self.region} if self.region else {}
                try:
                    self.client.make_bucket(self.bucket, **kwargs)
                except Exception as exc:
                    raise DocumentStorageError("创建 S3 Bucket 失败") from exc
            self._bucket_ready = True

    def _object_exists_sync(self, object_key: str) -> bool:
        try:
            self.client.stat_object(self.bucket, object_key)
            return True
        except Exception as exc:
            if _is_not_found_error(exc):
                return False
            raise DocumentStorageError("检查 S3 对象是否存在失败") from exc

    async def save_file(self, source_path: Path, object_key: str) -> None:
        """上传临时文件；上传成功后才删除本地临时文件。"""

        validate_object_key(object_key)
        await asyncio.to_thread(self._ensure_bucket_sync)
        if await asyncio.to_thread(self._object_exists_sync, object_key):
            raise FileExistsError(f"文档对象已经存在：{object_key}")
        try:
            await asyncio.to_thread(
                self.client.fput_object,
                self.bucket,
                object_key,
                str(source_path),
            )
        except Exception as exc:
            raise DocumentStorageError(f"上传 S3 对象失败：{object_key}") from exc
        await asyncio.to_thread(source_path.unlink, missing_ok=True)

    async def delete_file(self, object_key: str) -> None:
        """幂等删除 S3 对象；对象不存在时 S3 删除语义仍视为成功。"""

        validate_object_key(object_key)
        await asyncio.to_thread(self._ensure_bucket_sync)
        try:
            await asyncio.to_thread(
                self.client.remove_object,
                self.bucket,
                object_key,
            )
        except Exception as exc:
            raise DocumentStorageError(f"删除 S3 对象失败：{object_key}") from exc

    async def download_file(
        self,
        object_key: str,
        destination_path: Path,
    ) -> None:
        """把远程对象下载到 Worker 临时目录，供同步解析库读取。"""

        validate_object_key(object_key)
        await asyncio.to_thread(self._ensure_bucket_sync)
        await asyncio.to_thread(
            destination_path.parent.mkdir,
            parents=True,
            exist_ok=True,
        )
        try:
            await asyncio.to_thread(
                self.client.fget_object,
                self.bucket,
                object_key,
                str(destination_path),
            )
        except Exception as exc:
            if _is_not_found_error(exc):
                raise FileNotFoundError(
                    f"知识文档对象不存在：{object_key}"
                ) from exc
            raise DocumentStorageError(f"下载 S3 对象失败：{object_key}") from exc

    async def stream_file(
        self,
        object_key: str,
        chunk_size: int = 64 * 1024,
    ) -> AsyncIterator[bytes]:
        """以固定块大小读取远程响应，浏览器中断时也释放连接。"""

        if chunk_size <= 0:
            raise ValueError("文件读取块大小必须大于 0")
        validate_object_key(object_key)
        await asyncio.to_thread(self._ensure_bucket_sync)
        try:
            response = await asyncio.to_thread(
                self.client.get_object,
                self.bucket,
                object_key,
            )
        except Exception as exc:
            if _is_not_found_error(exc):
                raise FileNotFoundError(
                    f"知识文档对象不存在：{object_key}"
                ) from exc
            raise DocumentStorageError(f"读取 S3 对象失败：{object_key}") from exc

        try:
            while True:
                try:
                    chunk = await asyncio.to_thread(response.read, chunk_size)
                except Exception as exc:
                    raise DocumentStorageError(
                        f"流式读取 S3 对象失败：{object_key}"
                    ) from exc
                if not chunk:
                    break
                yield chunk
        finally:
            await asyncio.to_thread(self._close_response_sync, response)

    @staticmethod
    def _close_response_sync(response: Any) -> None:
        """关闭响应并把连接归还连接池。

        功能：无论 ``close`` 是否报错，都继续执行 ``release_conn``。

        作用：作为流式下载的统一清理动作，保证长时间运行的 API 进程不会因为连接
        未归还而逐渐耗尽连接池。

        为什么用它：MinIO 官方文档要求两步都执行；使用 ``try/finally`` 比连续调用
        更可靠，并通过 ``asyncio.to_thread`` 避免同步清理阻塞事件循环。
        """

        try:
            response.close()
        finally:
            response.release_conn()

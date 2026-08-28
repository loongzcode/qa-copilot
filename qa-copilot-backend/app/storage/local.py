import asyncio
import shutil
from collections.abc import AsyncIterator
from pathlib import Path, PurePosixPath

from app.storage.base import validate_object_key


class LocalDocumentStorage:
    """开发和单机部署使用的本地知识文档存储。"""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()

    def _resolve_object_key(self, object_key: str) -> Path:
        """把对象键安全地解析到存储根目录内，阻止路径穿越。"""

        validate_object_key(object_key)
        key_path = PurePosixPath(object_key)
        destination = self.root_dir.joinpath(*key_path.parts).resolve()
        if not destination.is_relative_to(self.root_dir):
            raise ValueError("文档对象键超出存储目录")

        return destination

    @staticmethod
    def _save_file_sync(source_path: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise FileExistsError(f"文档对象已经存在：{destination.name}")
        shutil.move(str(source_path), str(destination))

    async def save_file(self, source_path: Path, object_key: str) -> None:
        """在线程中移动文件，避免磁盘操作阻塞 FastAPI 事件循环。"""

        destination = self._resolve_object_key(object_key)
        await asyncio.to_thread(self._save_file_sync, source_path, destination)

    async def delete_file(self, object_key: str) -> None:
        """幂等删除本地对象。"""

        destination = self._resolve_object_key(object_key)
        await asyncio.to_thread(destination.unlink, missing_ok=True)

    @staticmethod
    def _download_file_sync(source: Path, destination: Path) -> None:
        if not source.is_file():
            raise FileNotFoundError(f"知识文档对象不存在：{source.name}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    async def download_file(self, object_key: str, destination_path: Path) -> None:
        """复制对象到 Worker 临时目录；生产存储实现可在这里从 S3/MinIO 下载。"""

        source = self._resolve_object_key(object_key)
        await asyncio.to_thread(self._download_file_sync, source, destination_path)


    async def stream_file(self,object_key: str, chunk_size: int = 64 * 1024,) -> AsyncIterator[bytes]:
        """分块读取本地文件，避免一次性把整个文件加载到内存。"""

        if chunk_size <= 0:
            raise ValueError("文件读取块大小必须大于 0")

        # 继续复用原来的安全路径校验，防止通过 ../ 读取存储目录外的文件。
        source = self._resolve_object_key(object_key)

        if not source.is_file():
            raise FileNotFoundError(
                f"知识文档对象不存在：{source.name}"
            )

        # 普通文件打开操作是同步的，交给线程执行。
        stream = await asyncio.to_thread(source.open, "rb")

        try:
            while True:
                # 每次只读取固定大小的一块，而不是一次读取整个文件。
                chunk = await asyncio.to_thread(
                    stream.read,
                    chunk_size,
                )

                # b"" 表示已经读取到文件末尾。
                if not chunk:
                    break

                # 把当前块交给 StreamingResponse。
                yield chunk
        finally:
            # 即使浏览器中途关闭连接，也要关闭文件句柄。
            await asyncio.to_thread(stream.close)

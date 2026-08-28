from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, settings
from app.storage.base import DocumentStorage
from app.storage.local import LocalDocumentStorage
from app.storage.s3 import S3DocumentStorage


def build_document_storage(config: Settings) -> DocumentStorage:
    """根据应用配置创建统一的文档存储实现。

    功能：在本地磁盘和 S3 兼容对象存储之间进行唯一一次实现选择。
    作用：FastAPI 依赖和 Celery Worker 都调用这里，保证上传、索引、预览和删除
    使用同一后端；Service 本身继续只认识 ``DocumentStorage`` 接口。
    为什么用它：如果 API 和 Worker 各自判断配置，很容易出现上传到 S3、Worker
    却去本地读取的错误。集中工厂也让新增存储后端时无需修改业务 Service。
    """

    if config.knowledge_document_storage_backend == "local":
        return LocalDocumentStorage(config.knowledge_document_storage_dir)

    endpoint = config.knowledge_document_s3_endpoint
    access_key = config.knowledge_document_s3_access_key
    secret_key = config.knowledge_document_s3_secret_key
    if endpoint is None or access_key is None or secret_key is None:
        # 正常启动时 Settings 校验器会更早给出完整缺失项；这里保留防御检查，
        # 也方便测试或其他代码直接传入自定义配置对象。
        raise ValueError("S3/MinIO 存储连接配置不完整")

    session_token = config.knowledge_document_s3_session_token
    return S3DocumentStorage(
        endpoint=endpoint,
        access_key=access_key.get_secret_value(),
        secret_key=secret_key.get_secret_value(),
        session_token=(
            session_token.get_secret_value()
            if session_token is not None
            else None
        ),
        bucket=config.knowledge_document_s3_bucket,
        secure=config.knowledge_document_s3_secure,
        region=config.knowledge_document_s3_region,
        auto_create_bucket=config.knowledge_document_s3_auto_create_bucket,
    )


@lru_cache(maxsize=1)
def get_document_storage() -> DocumentStorage:
    """返回当前进程复用的存储客户端，避免每个请求重新创建连接池。"""

    return build_document_storage(settings)

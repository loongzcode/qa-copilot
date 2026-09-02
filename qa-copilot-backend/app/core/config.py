from functools import lru_cache
from ipaddress import ip_network
from pathlib import Path
from typing import Literal, Self

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Agent 技术情报后台"
    app_env: str = "development"
    debug: bool = True
    api_prefix: str = "/api"

    # Model Context Protocol（模型上下文协议）通过同一个 FastAPI 进程提供
    # Streamable HTTP 入口。issuer 是令牌签发方，resource URL 是 MCP 客户端连接地址。
    mcp_enabled: bool = True
    mcp_issuer_url: str = "http://127.0.0.1:8000"
    mcp_resource_server_url: str = "http://127.0.0.1:8000/api/mcp/"

    redis_url: str = "redis://localhost:6379/1"

    # FastAPI 始终通过 /metrics 暴露指标；Celery Worker 是独立进程，配置非 0
    # 端口后会额外启动只提供 Prometheus 指标的 HTTP 服务。
    metrics_enabled: bool = True
    metrics_worker_host: str = "0.0.0.0"
    metrics_worker_port: int = Field(default=0, ge=0, le=65535)

    # 发件箱发布器每次最多认领多少条事件，限制单个周期的数据库和 Redis 压力。
    outbox_publish_batch_size: int = Field(default=20, ge=1, le=500)
    # Celery Beat 每隔多少秒触发一次发件箱发布任务。
    outbox_publish_interval_seconds: int = Field(default=2, ge=1, le=300)
    # 发布失败后的指数退避起始时间和最大等待时间。
    outbox_retry_base_seconds: int = Field(default=5, ge=1, le=3600)
    outbox_retry_max_seconds: int = Field(default=300, ge=1, le=86400)
    # PROCESSING 事件超过该时长仍未完成，说明发布器可能在发送期间退出。
    outbox_processing_timeout_seconds: int = Field(default=120, ge=10, le=86400)
    # 补偿任务执行频率及每轮最多处理的数据量。
    background_recovery_interval_seconds: int = Field(default=60, ge=10, le=3600)
    background_recovery_batch_size: int = Field(default=100, ge=1, le=1000)
    # 已提交文档等待 Worker 与执行阶段允许的最长静默时间。
    knowledge_document_pending_timeout_seconds: int = Field(default=180, ge=30, le=86400)
    knowledge_document_processing_timeout_seconds: int = Field(default=1800, ge=60, le=86400)
    knowledge_document_max_recoveries: int = Field(default=3, ge=0, le=20)
    # 其余 AI/工具后台任务没有持续心跳时，使用更新时间判断是否已经失去 Worker。
    background_pending_timeout_seconds: int = Field(default=300, ge=30, le=86400)
    background_running_timeout_seconds: int = Field(default=3600, ge=60, le=86400)
    # Supervisor Worker 长时间不推进步骤时重新投递；超过次数后收口失败，避免无限重试写能力。
    supervisor_running_timeout_seconds: int = Field(default=600, ge=60, le=86400)
    supervisor_max_recoveries: int = Field(default=3, ge=0, le=20)

    database_url: str = "postgresql+asyncpg://postgres:password@127.0.0.1:5432/rag_fastapi"
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:9527", "http://localhost:5173"])

    secret_key: str = "development-only-secret-key-change-me"
    data_encryption_key: SecretStr
    data_encryption_previous_keys: list[SecretStr] = Field(default_factory=list)
    test_env_allowed_private_networks: list[str] = Field(default_factory=list)
    test_env_allow_loopback: bool = False
    # 通知 Webhook/SMTP 默认只能访问公网；企业内网地址必须显式加入允许网段。
    notification_allowed_private_networks: list[str] = Field(default_factory=list)
    notification_allow_loopback: bool = False
    # MySQL、Nacos 和业务 API 默认拒绝私网/回环；企业内网和本地联调需显式放行。
    tool_allowed_private_networks: list[str] = Field(default_factory=list)
    tool_allow_loopback: bool = False
    # Text-to-SQL（自然语言转 SQL）查询的服务端硬限制；前端传值不能突破这些上限。
    data_query_default_timeout_seconds: int = Field(default=30, ge=1, le=300)
    data_query_max_timeout_seconds: int = Field(default=60, ge=1, le=600)
    data_query_default_row_limit: int = Field(default=200, ge=1, le=5000)
    data_query_max_row_limit: int = Field(default=1000, ge=1, le=10000)
    data_query_max_result_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    data_query_max_generation_retries: int = Field(default=2, ge=0, le=5)
    data_query_max_metadata_tables: int = Field(default=500, ge=1, le=5000)
    data_query_explain_row_threshold: int = Field(default=1_000_000, ge=1, le=1_000_000_000)
    # 单次自动化任务允许的默认和最大总执行时间；每个请求还有定义内的独立超时。
    automation_execution_default_timeout_seconds: int = Field(default=300, ge=10, le=3600)
    automation_execution_max_timeout_seconds: int = Field(default=1800, ge=30, le=7200)
    # 防止被测接口返回超大正文耗尽 Worker 内存。
    automation_response_max_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    # 受控执行子进程的短期输入/输出目录；每次任务退出后都会删除对应子目录。
    automation_execution_temp_dir: Path = Path("data/automation-executions")
    # Worker 异常退出后，超过任务总超时再等待这段宽限时间，补偿扫描才会收口状态。
    automation_execution_recovery_grace_seconds: int = Field(default=60, ge=0, le=3600)
    # local：开发机磁盘；s3/minio：使用同一套 S3 兼容远程存储实现。
    knowledge_document_storage_backend: Literal["local", "s3", "minio"] = "local"
    knowledge_document_storage_dir: Path = Path("data/knowledge-documents")
    knowledge_document_s3_endpoint: str | None = None
    knowledge_document_s3_access_key: SecretStr | None = None
    knowledge_document_s3_secret_key: SecretStr | None = None
    knowledge_document_s3_session_token: SecretStr | None = None
    knowledge_document_s3_bucket: str = "qa-copilot-documents"
    knowledge_document_s3_secure: bool = True
    knowledge_document_s3_region: str | None = None
    knowledge_document_s3_auto_create_bucket: bool = False
    knowledge_document_max_size_bytes: int = Field(
        default=20 * 1024 * 1024,
        gt=0,
        le=1024 * 1024 * 1024,
    )
    knowledge_document_chunk_size_tokens: int = Field(default=800, ge=100, le=4000)
    knowledge_document_chunk_overlap_tokens: int = Field(default=120, ge=0, le=1000)
    # 解析器单次交给切片器的最大字符数。即使 PDF 单页或 TXT 单行异常大，
    # 也会先拆成有限大小的段，避免一个解析结果造成内存尖峰。
    knowledge_document_section_max_chars: int = Field(
        default=64 * 1024,
        ge=4096,
        le=4 * 1024 * 1024,
    )
    # 单篇文档允许生成的切片数量和切片 Token 总量上限。Token 总量包含重叠区，
    # 因而同时约束 Embedding 成本、暂存表占用和后续检索规模。
    knowledge_document_max_chunks: int = Field(default=10_000, ge=1, le=1_000_000)
    knowledge_document_max_index_tokens: int = Field(
        default=500_000,
        ge=1000,
        le=100_000_000,
    )
    # 当前接入的 OpenAI 兼容 Embedding 服务单次最多接收 20 条文本。
    # 保留环境变量后，可以针对限制更严格的服务商继续调小。
    knowledge_embedding_batch_size: int = Field(default=20, ge=1, le=20)
    # 测试用例生成属于结构化长输出任务。一次输入过多需求点会让模型输出达到上限，
    # 造成 JSON 在中途被截断；因此 Worker 按固定数量分批调用模型。
    case_generation_batch_size: int = Field(default=5, ge=1, le=20)
    # 一次最多从数据库读取多少条最近消息，防止无上限查询。
    knowledge_chat_recent_message_limit: int = Field(
        default=20,
        ge=2,
        le=100,
    )

    # 为消息角色、JSON 包装和不同模型分词差异预留安全空间。
    knowledge_chat_context_safety_tokens: int = Field(
        default=512,
        ge=128,
        le=8192,
    )
    # 问题改写只需要最近少量对话，不应把整个长会话交给改写模型。
    knowledge_chat_query_rewrite_token_budget: int = Field(
        default=2048,
        ge=256,
        le=16384,
    )

    # 未压缩消息累计到多少 Token 时触发压缩。
    knowledge_chat_memory_trigger_tokens: int = Field(
        default=6000,
        ge=1000,
        le=200000,
    )
    # 压缩时保留最近多少 Token 的原始消息。
    knowledge_chat_memory_keep_recent_tokens: int = Field(
        default=2000,
        ge=256,
        le=50000,
    )
    # 限制模型最多生成多长的摘要。
    knowledge_chat_memory_summary_max_tokens: int = Field(
        default=1200,
        ge=128,
        le=8192,
    )
    # 每次提问最多召回几条相关历史摘要。
    knowledge_chat_memory_retrieval_top_k: int = Field(
        default=3,
        ge=1,
        le=20,
    )
    # 召回的摘要总共最多占用多少 Token。
    knowledge_chat_memory_retrieval_token_budget: int = Field(
        default=1500,
        ge=256,
        le=16384,
    )

    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    @field_validator("data_encryption_key")
    @classmethod
    def validate_data_encryption_key(cls, value: SecretStr) -> SecretStr:
        """启动时校验主数据加密密钥，避免运行到解密时才发现配置错误。"""

        try:
            Fernet(value.get_secret_value())
        except (TypeError, ValueError) as exc:
            raise ValueError("DATA_ENCRYPTION_KEY 必须是合法的 Fernet 密钥") from exc
        return value

    @field_validator("data_encryption_previous_keys")
    @classmethod
    def validate_previous_data_encryption_keys(
        cls,
        values: list[SecretStr],
    ) -> list[SecretStr]:
        """旧密钥只用于轮换期间解密历史数据。"""

        for value in values:
            try:
                Fernet(value.get_secret_value())
            except (TypeError, ValueError) as exc:
                raise ValueError("DATA_ENCRYPTION_PREVIOUS_KEYS 中存在非法 Fernet 密钥") from exc
        return values

    @model_validator(mode="after")
    def validate_chunk_settings(self) -> Self:
        """重叠区必须小于切片大小，否则递归切片器无法向前推进。"""

        if self.knowledge_document_chunk_overlap_tokens >= self.knowledge_document_chunk_size_tokens:
            raise ValueError("KNOWLEDGE_DOCUMENT_CHUNK_OVERLAP_TOKENS 必须小于切片大小")
        return self

    @model_validator(mode="after")
    def validate_document_storage_settings(self) -> Self:
        """启用 S3/MinIO 时提前校验连接所需配置。

        功能：检查 endpoint、访问密钥、私钥和 Bucket。
        作用：应用启动阶段就暴露配置错误，避免用户上传文件时才失败。
        为什么用它：这些字段在本地模式下不需要，因此不能逐字段设为必填；使用
        模型级校验可以根据所选后端实施条件必填。
        """

        if self.knowledge_document_storage_backend == "local":
            return self

        required_values = {
            "KNOWLEDGE_DOCUMENT_S3_ENDPOINT": self.knowledge_document_s3_endpoint,
            "KNOWLEDGE_DOCUMENT_S3_ACCESS_KEY": (
                self.knowledge_document_s3_access_key.get_secret_value()
                if self.knowledge_document_s3_access_key is not None
                else None
            ),
            "KNOWLEDGE_DOCUMENT_S3_SECRET_KEY": (
                self.knowledge_document_s3_secret_key.get_secret_value()
                if self.knowledge_document_s3_secret_key is not None
                else None
            ),
            "KNOWLEDGE_DOCUMENT_S3_BUCKET": self.knowledge_document_s3_bucket,
        }
        missing = [name for name, value in required_values.items() if not value]
        if missing:
            raise ValueError("S3/MinIO 存储缺少配置：" + ", ".join(missing))
        if "://" in (self.knowledge_document_s3_endpoint or ""):
            raise ValueError("KNOWLEDGE_DOCUMENT_S3_ENDPOINT 只能填写 host:port，不能包含 http:// 或 https://")
        return self

    @model_validator(mode="after")
    def validate_knowledge_chat_memory_settings(self) -> Self:
        """保证触发压缩时确实存在可以被压缩的较早消息。"""

        if self.knowledge_chat_memory_keep_recent_tokens >= self.knowledge_chat_memory_trigger_tokens:
            raise ValueError("KNOWLEDGE_CHAT_MEMORY_KEEP_RECENT_TOKENS 必须小于 KNOWLEDGE_CHAT_MEMORY_TRIGGER_TOKENS")
        return self

    @model_validator(mode="after")
    def validate_outbox_retry_settings(self) -> Self:
        """保证发件箱指数退避的起始等待时间不大于最大等待时间。"""

        if self.outbox_retry_base_seconds > self.outbox_retry_max_seconds:
            raise ValueError("OUTBOX_RETRY_BASE_SECONDS 不能大于 OUTBOX_RETRY_MAX_SECONDS")
        return self

    @model_validator(mode="after")
    def validate_automation_timeout_settings(self) -> Self:
        """默认自动化超时不能超过平台允许的最大超时。"""
        if self.automation_execution_default_timeout_seconds > self.automation_execution_max_timeout_seconds:
            raise ValueError("AUTOMATION_EXECUTION_DEFAULT_TIMEOUT_SECONDS 不能大于最大超时")
        return self

    @field_validator("test_env_allowed_private_networks")
    @classmethod
    def validate_test_env_private_networks(cls, values: list[str]) -> list[str]:
        """只允许平台运维配置 RFC1918 或 IPv6 ULA 私网子网。"""

        allowed_roots = (
            ip_network("10.0.0.0/8"),
            ip_network("172.16.0.0/12"),
            ip_network("192.168.0.0/16"),
            ip_network("fc00::/7"),
        )
        normalized: list[str] = []

        for value in values:
            try:
                network = ip_network(value.strip(), strict=False)
            except ValueError as exc:
                raise ValueError(f"TEST_ENV_ALLOWED_PRIVATE_NETWORKS 包含非法 CIDR：{value}") from exc

            inside_allowed_root = any(
                network.version == root.version and network.subnet_of(root) for root in allowed_roots
            )
            if not inside_allowed_root:
                raise ValueError("TEST_ENV_ALLOWED_PRIVATE_NETWORKS 只允许 RFC1918 或 IPv6 ULA 子网")

            normalized_network = str(network)
            if normalized_network not in normalized:
                normalized.append(normalized_network)

        return normalized

    @field_validator("notification_allowed_private_networks")
    @classmethod
    def validate_notification_private_networks(
        cls,
        values: list[str],
    ) -> list[str]:
        """校验通知服务允许访问的企业私网网段。

        功能：解析无类别域间路由（Classless Inter-Domain Routing，CIDR）网段，
        并限制为常见 IPv4 私网或 IPv6 唯一本地地址。

        作用：供 Webhook 和邮件服务器目标校验复用，只有运维显式配置的企业
        内网才允许被后台 Worker 访问。

        为什么用它：通知地址由管理员填写，仍可能被误配成云元数据等敏感地址；
        启动时白名单校验能缩小服务端请求伪造的攻击范围。
        """
        allowed_roots = (
            ip_network("10.0.0.0/8"),
            ip_network("172.16.0.0/12"),
            ip_network("192.168.0.0/16"),
            ip_network("fc00::/7"),
        )
        normalized: list[str] = []
        for value in values:
            try:
                network = ip_network(value.strip(), strict=False)
            except ValueError as exc:
                raise ValueError(f"NOTIFICATION_ALLOWED_PRIVATE_NETWORKS 包含非法 CIDR：{value}") from exc
            if not any(network.version == root.version and network.subnet_of(root) for root in allowed_roots):
                raise ValueError("NOTIFICATION_ALLOWED_PRIVATE_NETWORKS 只允许私网或 IPv6 ULA 子网")
            normalized_network = str(network)
            if normalized_network not in normalized:
                normalized.append(normalized_network)
        return normalized

    @field_validator("tool_allowed_private_networks")
    @classmethod
    def validate_tool_private_networks(cls, values: list[str]) -> list[str]:
        """只允许将企业私网 CIDR 加入工具执行器网络白名单。"""
        allowed_roots = (
            ip_network("10.0.0.0/8"),
            ip_network("172.16.0.0/12"),
            ip_network("192.168.0.0/16"),
            ip_network("fc00::/7"),
        )
        normalized: list[str] = []
        for value in values:
            try:
                network = ip_network(value.strip(), strict=False)
            except ValueError as exc:
                raise ValueError(f"TOOL_ALLOWED_PRIVATE_NETWORKS 包含非法 CIDR：{value}") from exc
            if not any(network.version == root.version and network.subnet_of(root) for root in allowed_roots):
                raise ValueError("TOOL_ALLOWED_PRIVATE_NETWORKS 只允许私网或 IPv6 ULA 子网")
            normalized_value = str(network)
            if normalized_value not in normalized:
                normalized.append(normalized_value)
        return normalized


@lru_cache
def get_settings() -> Settings:
    """缓存配置对象，保证整个进程内读取到一致的配置。"""

    return Settings()


settings = get_settings()

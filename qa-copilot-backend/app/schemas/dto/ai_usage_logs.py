from datetime import datetime
from typing import Self

from pydantic import Field, field_validator, model_validator

from app.core.constants import AIUsageStatus
from app.schemas.camel_model import CamelModel


class AIUsageLogsFilterDTO(CamelModel):
    """调用日志列表和统计接口共用的筛选条件。"""

    # 按 AI 服务商主键筛选，例如只查看阿里云百炼产生的调用。
    provider_id: int | None = Field(default=None, gt=0)
    # 按平台中的 AI 模型配置主键筛选，不是服务商提供的字符串模型标识。
    model_id: int | None = Field(default=None, gt=0)
    # 按发起调用的系统用户筛选；后台 Worker 无明确用户时可以为空。
    user_id: int | None = Field(default=None, gt=0)
    # 按业务所属项目筛选；连接测试等系统级调用可以不属于具体项目。
    project_id: int | None = Field(default=None, gt=0)
    # 调用用途，例如 embedding、rerank、knowledge_qa 或 query_rewrite。
    task_type: str | None = Field(default=None, max_length=40)
    # 调用最终状态；当前只区分成功和失败。
    status: AIUsageStatus | None = None
    # 同一个 HTTP 请求链路使用相同 request_id，便于串联排查一次请求。
    request_id: str | None = Field(default=None, max_length=64)
    # Celery 任务或生成批次的标识，用于追踪异步业务任务。
    task_id: str | None = Field(default=None, max_length=128)
    # 只查询该时间及之后产生的日志。
    start_time: datetime | None = None
    # 只查询该时间及之前产生的日志。
    end_time: datetime | None = None

    @field_validator("task_type", "request_id", "task_id", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        """去除筛选文本两端空格，并把空字符串视为没有传筛选条件。"""
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def validate_time_range(self) -> Self:
        """开始和结束时间需要一起比较，所以使用模型级校验器。"""
        if self.start_time is not None and self.end_time is not None:
            if self.start_time > self.end_time:
                raise ValueError("开始时间不能晚于结束时间")
        return self


class AIUsageLogsQueryDTO(AIUsageLogsFilterDTO):
    """调用日志分页列表参数，在公共筛选条件上增加页码。"""

    # 当前查询第几页，从第 1 页开始。
    current: int = Field(default=1, ge=1)
    # 每页最多返回 100 条，防止一次读取过多日志。
    size: int = Field(default=10, ge=1, le=100)


class AIUsageLogsCreateDTO(CamelModel):
    """内部记录一次 AI 调用时使用的数据，不直接开放给前端创建日志。"""

    # 本次调用使用的服务商配置主键。
    provider_id: int = Field(gt=0)
    # 本次调用使用的模型配置主键。
    model_id: int = Field(gt=0)
    # 调用发生时的服务商名称快照，避免配置删除后日志失去可读名称。
    provider_name: str = Field(min_length=1, max_length=100)
    # 调用发生时的平台模型名称快照。
    model_name: str = Field(min_length=1, max_length=100)
    # 贯穿一次 HTTP 请求的追踪标识；Worker 独立执行时可以为空。
    request_id: str | None = Field(default=None, max_length=64)
    # 发起调用的用户；没有明确用户的后台任务可以为空。
    user_id: int | None = Field(default=None, gt=0)
    # 调用所属项目；系统级模型测试可以为空。
    project_id: int | None = Field(default=None, gt=0)
    # 异步任务、生成批次或其他业务任务标识。
    task_id: str | None = Field(default=None, max_length=128)
    # AI 调用的业务用途。
    task_type: str = Field(min_length=1, max_length=40)
    # AI 调用是成功还是失败。
    status: AIUsageStatus = AIUsageStatus.SUCCESS
    # 发送给模型的实际输入 Token 数；服务商未返回时允许使用本地估算值。
    input_tokens: int = Field(default=0, ge=0)
    # 模型实际生成的输出 Token 数。
    output_tokens: int = Field(default=0, ge=0)
    # 本次调用总 Token；通常等于输入 Token 加输出 Token。
    total_tokens: int = Field(default=0, ge=0)
    # 从发起请求到收到结果的耗时，单位为毫秒。
    latency_ms: int = Field(default=0, ge=0)
    # 知识检索最终命中的候选数量；非检索任务保持为 0。
    retrieval_hit_count: int = Field(default=0, ge=0)
    # 失败时保存脱敏后的异常摘要，禁止写入密钥、Authorization 或完整 Prompt。
    error_message: str | None = Field(default=None, max_length=2000)

class AIUsageContextDTO(CamelModel):
    """一次 AI 调用所属的业务上下文。"""

    # 同一次 HTTP 请求的链路标识。
    request_id: str | None = Field(default=None, max_length=64)

    # 发起调用的登录用户；后台任务没有明确用户时为空。
    user_id: int | None = Field(default=None, gt=0)

    # 调用所属项目；模型连接测试等系统调用可以为空。
    project_id: int | None = Field(default=None, gt=0)

    # Celery 任务、生成批次或其他业务任务标识。
    task_id: str | None = Field(default=None, max_length=128)

    # 知识检索最终命中的资料数量；非检索任务保持为 0。
    retrieval_hit_count: int = Field(default=0, ge=0)

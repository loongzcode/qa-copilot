from datetime import datetime

from app.core.constants import AIUsageStatus
from app.schemas.camel_model import CamelModel


class AIUsageLogListVO(CamelModel):
    """调用日志列表的一行，只返回表格展示所需的字段。"""

    # 调用日志主键，用于继续查询详情。
    id: int
    # HTTP 请求追踪标识；后台任务没有请求链路时为空。
    request_id: str | None
    # 异步任务或业务生成批次标识。
    task_id: str | None
    # 调用用户主键；后台任务没有明确用户时为空。
    user_id: int | None
    # 调用用户名称；用户不存在或后台任务调用时为空。
    user_name: str | None
    # 所属项目主键；系统级调用可以为空。
    project_id: int | None
    # 所属项目名称，便于管理员直接识别业务来源。
    project_name: str | None
    # 服务商主键；服务商删除后日志仍可保留名称快照。
    provider_id: int | None
    # 调用发生时的服务商名称快照。
    provider_name: str
    # 模型配置主键；模型删除后可以为空。
    model_id: int | None
    # 调用发生时的平台模型名称快照。
    model_name: str
    # 调用用途，例如知识问答、Embedding 或 Rerank。
    task_type: str
    # 调用最终状态。
    status: AIUsageStatus
    # 输入 Token 数。
    input_tokens: int
    # 输出 Token 数。
    output_tokens: int
    # 输入和输出的总 Token 数。
    total_tokens: int
    # 调用耗时，单位为毫秒。
    latency_ms: int
    # 日志产生时间。
    created_at: datetime


class AIUsageLogDetailVO(AIUsageLogListVO):
    """单条调用日志详情，在列表字段上补充排障信息。"""

    # 知识检索最终命中的资料数量；非检索任务通常为 0。
    retrieval_hit_count: int
    # 失败原因的脱敏摘要；成功调用时为空。
    error_message: str | None


class AIUsageLogStatisticsVO(CamelModel):
    """当前筛选范围内的调用次数、Token 和耗时汇总。"""

    # 符合筛选条件的全部调用次数。
    total_calls: int
    # 成功完成的调用次数。
    success_calls: int
    # 调用失败的次数。
    failed_calls: int
    # 成功调用占总调用的百分比，范围为 0 到 100。
    success_rate: float
    # 累计输入 Token 数。
    input_tokens: int
    # 累计输出 Token 数。
    output_tokens: int
    # 累计总 Token 数。
    total_tokens: int
    # 平均调用耗时，单位为毫秒。
    average_latency_ms: float
    # 最慢一次调用的耗时，单位为毫秒。
    max_latency_ms: int
    # 95% 的调用都不会超过该耗时，用于观察大多数用户的真实体验。
    p95_latency_ms: float

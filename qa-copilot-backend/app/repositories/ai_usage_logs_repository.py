"""AI 调用日志的筛选、分页、详情和聚合查询。"""
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.core.constants import AIUsageStatus
from app.models import AIUsageLog
from app.repositories.base_repository import BaseRepository
from app.schemas.dto.ai_usage_logs import (
    AIUsageLogsFilterDTO,
    AIUsageLogsQueryDTO,
)


@dataclass(frozen=True, slots=True)
class AIUsageLogStatisticsRecord:
    """Repository 聚合查询返回的内部统计结果，不直接返回给前端。"""

    # 当前筛选范围内全部 AI 调用次数。
    total_calls: int
    # status 为 success 的调用次数。
    success_calls: int
    # status 为 failed 的调用次数。
    failed_calls: int
    # 所有调用累计使用的输入 Token。
    input_tokens: int
    # 所有调用累计生成的输出 Token。
    output_tokens: int
    # 输入与输出 Token 的累计总和。
    total_tokens: int
    # 当前筛选范围内一次调用的平均耗时，单位为毫秒。
    average_latency_ms: float
    # 当前筛选范围内最慢一次调用的耗时，单位为毫秒。
    max_latency_ms: int
    # 95% 调用不会超过的耗时，单位为毫秒。
    p95_latency_ms: float


class AIUsageLogsRepository(BaseRepository):
    @staticmethod
    def _build_conditions(
            query: AIUsageLogsFilterDTO,
    ) -> list[ColumnElement[bool]]:
        """
        把前端实际传入的筛选参数转换成 SQL WHERE 条件。

        每个可选字段都必须先判断是否为 None。没有传表示“不限制该字段”，
        不能错误地生成 column IS NULL 条件。这个方法同时供列表和统计
        查询复用，保证两处使用完全相同的筛选范围。
        """
        conditions: list[ColumnElement[bool]] = []

        if query.provider_id is not None:
            conditions.append(
                AIUsageLog.provider_id == query.provider_id
            )

        if query.model_id is not None:
            conditions.append(
                AIUsageLog.model_id == query.model_id
            )

        if query.user_id is not None:
            conditions.append(
                AIUsageLog.user_id == query.user_id
            )

        if query.project_id is not None:
            conditions.append(
                AIUsageLog.project_id == query.project_id
            )

        if query.task_type is not None:
            conditions.append(
                AIUsageLog.task_type == query.task_type
            )

        if query.status is not None:
            conditions.append(
                AIUsageLog.status == query.status.value
            )

        if query.request_id is not None:
            conditions.append(
                AIUsageLog.request_id == query.request_id
            )

        if query.task_id is not None:
            conditions.append(
                AIUsageLog.task_id == query.task_id
            )

        if query.start_time is not None:
            conditions.append(
                AIUsageLog.created_at >= query.start_time
            )

        if query.end_time is not None:
            conditions.append(
                AIUsageLog.created_at <= query.end_time
            )

        return conditions

    async def list_logs(
            self,
            query: AIUsageLogsQueryDTO,
    ) -> tuple[list[AIUsageLog], int]:
        """按筛选条件查询当前页日志，并返回符合条件的总记录数。"""
        conditions = self._build_conditions(query)

        # count 查询只计算总数量，不需要加载用户、项目或整行日志。
        count_statement = (
            select(func.count())
            .select_from(AIUsageLog)
            .where(*conditions)
        )
        total = int(
            await self.session.scalar(count_statement)
            or 0
        )

        # offset 表示跳过前面多少条，例如第 2 页、每页 10 条需要跳过 10 条。
        offset = (query.current - 1) * query.size

        statement = (
            select(AIUsageLog)
            # Service 要显示用户名和项目名，因此在查询日志时一起加载这两个关系。
            .options(
                selectinload(AIUsageLog.user),
                selectinload(AIUsageLog.project),
            )
            .where(*conditions)
            # created_at 相同时再按 id 倒序，保证分页顺序始终稳定。
            .order_by(
                AIUsageLog.created_at.desc(),
                AIUsageLog.id.desc(),
            )
            .offset(offset)
            .limit(query.size)
        )
        usage_logs = list(
            (
                await self.session.scalars(statement)
            ).all()
        )

        return usage_logs, total

    async def get_log_detail(self, log_id: int) -> AIUsageLog | None:
        statement = (
            select(AIUsageLog)
            .options(
                selectinload(AIUsageLog.user),
                selectinload(AIUsageLog.project),
            )
            .where(AIUsageLog.id == log_id)
        )

        return await self.session.scalar(statement)

    async def get_statistics(
            self,
            query: AIUsageLogsFilterDTO,
    ) -> AIUsageLogStatisticsRecord:
        conditions = self._build_conditions(query)
        statement = (
            select(
                # 符合筛选条件的全部调用次数。
                func.count(AIUsageLog.id).label("total_calls"),
                # 只统计成功调用；FILTER 相当于给这个 COUNT 单独增加条件。
                func.count(AIUsageLog.id).filter(
                    AIUsageLog.status == AIUsageStatus.SUCCESS.value
                ).label("success_calls"),
                # 只统计失败调用。
                func.count(AIUsageLog.id).filter(
                    AIUsageLog.status == AIUsageStatus.FAILED.value
                ).label("failed_calls"),
                # 没有匹配日志时 SUM 会返回 NULL，因此使用 coalesce 转成 0。
                func.coalesce(
                    func.sum(AIUsageLog.input_tokens),
                    0,
                ).label("input_tokens"),
                # 累计输出 Token。
                func.coalesce(
                    func.sum(AIUsageLog.output_tokens),
                    0
                ).label("output_tokens"),
                # 累计输入与输出的总 Token。
                func.coalesce(
                    func.sum(AIUsageLog.total_tokens),
                    0
                ).label("total_tokens"),
                # 平均调用耗时；没有数据时返回 0。
                func.coalesce(
                    func.avg(AIUsageLog.latency_ms),
                    0,
                ).label("average_latency_ms"),
                # 最慢一次调用的耗时。
                func.coalesce(
                    func.max(AIUsageLog.latency_ms),
                    0,
                ).label("max_latency_ms"),
                # 按耗时排序后取 95% 位置的值，用来观察绝大多数请求的体验。
                func.coalesce(
                    func.percentile_cont(0.95).within_group(
                        AIUsageLog.latency_ms
                    ),
                    0,
                ).label("p95_latency_ms")
            )
            .select_from(AIUsageLog)
            .where(*conditions)
        )
        # 聚合查询即使没有匹配记录也会返回一行，所以这里使用 one()。
        row = (
            await self.session.execute(statement)
        ).one()
        # SQL 聚合值可能是 Decimal 等数据库类型，统一转换成 VO 需要的 Python 类型。
        return AIUsageLogStatisticsRecord(
            total_calls=int(row.total_calls),
            success_calls=int(row.success_calls),
            failed_calls=int(row.failed_calls),
            input_tokens=int(row.input_tokens),
            output_tokens=int(row.output_tokens),
            total_tokens=int(row.total_tokens),
            average_latency_ms=float(row.average_latency_ms),
            max_latency_ms=int(row.max_latency_ms),
            p95_latency_ms=float(row.p95_latency_ms)
        )

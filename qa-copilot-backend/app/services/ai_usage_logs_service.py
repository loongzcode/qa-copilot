"""AI 调用日志的查询、脱敏和统计业务。"""
from app.exceptions import NotFoundException
from app.models import AIUsageLog
from app.repositories.ai_usage_logs_repository import AIUsageLogsRepository
from app.schemas.dto.ai_usage_logs import AIUsageLogsFilterDTO, AIUsageLogsQueryDTO
from app.schemas.vo.ai_usage_logs import AIUsageLogDetailVO, AIUsageLogListVO, AIUsageLogStatisticsVO


class AIUsageLogsService:
    def __init__(self, repository: AIUsageLogsRepository):
        self.repository = repository

    @staticmethod
    def _usage_log_list_read(
            usage_log: AIUsageLog,
    ) -> AIUsageLogListVO:
        """把数据库日志实体转换为前端列表中的一行数据。"""
        return AIUsageLogListVO(
            # 日志自身的调用链、关联对象和模型快照。
            id=usage_log.id,
            request_id=usage_log.request_id,
            task_id=usage_log.task_id,
            user_id=usage_log.user_id,
            user_name=(
                usage_log.user.display_name
                if usage_log.user is not None
                else None
            ),
            project_id=usage_log.project_id,
            project_name=(
                usage_log.project.name
                if usage_log.project is not None
                else None
            ),
            provider_id=usage_log.provider_id,
            provider_name=usage_log.provider_name,
            model_id=usage_log.model_id,
            model_name=usage_log.model_name,
            # 调用用途、执行结果、Token、耗时和发生时间。
            task_type=usage_log.task_type,
            status=usage_log.status,
            input_tokens=usage_log.input_tokens,
            output_tokens=usage_log.output_tokens,
            total_tokens=usage_log.total_tokens,
            latency_ms=usage_log.latency_ms,
            created_at=usage_log.created_at
        )

    async def list_logs(
            self,
            query: AIUsageLogsQueryDTO,
    ) -> tuple[list[AIUsageLogListVO], int]:
        usage_logs, total = await self.repository.list_logs(query)

        records = [
            self._usage_log_list_read(usage_log)
            for usage_log in usage_logs
        ]

        return records, total

    async def get_log_detail(
            self,
            log_id: int

    ) -> AIUsageLogDetailVO:
        usage_log = await self.repository.get_log_detail(log_id)
        if usage_log is None:
            raise NotFoundException("调用日志不存在")
        list_date = self._usage_log_list_read(usage_log).model_dump()
        return AIUsageLogDetailVO(
            **list_date,
            retrieval_hit_count=usage_log.retrieval_hit_count,
            error_message=usage_log.error_message,
        )

    async def get_statistics(
            self,
            query: AIUsageLogsFilterDTO,
    ) -> AIUsageLogStatisticsVO:
        log_statistics = await self.repository.get_statistics(query)
        # Repository 返回原始次数；百分比属于展示业务，由 Service 统一计算。
        success_rate = (
            round(
                log_statistics.success_calls /
                log_statistics.total_calls * 100, 2
            )
            if log_statistics.total_calls > 0
            else 0.0
        )
        return AIUsageLogStatisticsVO(
            total_calls = log_statistics.total_calls,
            success_calls = log_statistics.success_calls,
            failed_calls = log_statistics.failed_calls,
            success_rate = success_rate,
            input_tokens = log_statistics.input_tokens,
            output_tokens = log_statistics.output_tokens,
            total_tokens = log_statistics.total_tokens,
            average_latency_ms = log_statistics.average_latency_ms,
            max_latency_ms = log_statistics.max_latency_ms,
            p95_latency_ms = log_statistics.p95_latency_ms
        )

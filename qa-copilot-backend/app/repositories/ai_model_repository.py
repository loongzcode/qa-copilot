from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.models import AIModel, AIUsageLog
from app.repositories.base_repository import BaseRepository
from app.schemas.dto.ai_usage_logs import AIUsageLogsCreateDTO


class AIModelRepository(BaseRepository):
    async def list_models(self) -> list[AIModel]:
        return list(
            (
                await self.session.scalars(select(AIModel).options(selectinload(AIModel.provider)).order_by(AIModel.id))
            ).all()
        )

    async def get_model(self, model_pk: int, with_provider: bool = True) -> AIModel | None:
        statement = select(AIModel).where(AIModel.id == model_pk)
        if with_provider:
            statement = statement.options(selectinload(AIModel.provider))
        return (await self.session.scalars(statement)).one_or_none()

    async def clear_default_models(self):
        await self.session.execute(update(AIModel).values(is_default=False))

    async def record_usage(
            self,
            payload: AIUsageLogsCreateDTO,
    ) -> None:
        """保存一条已经完成校验和脱敏的 AI 调用日志。"""

        # 名称使用调用发生时的快照。以后服务商或模型配置被删除时，外键
        # 可以按数据库约束置空，但历史日志仍然保留当时可读的名称。
        usage_log = AIUsageLog(
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            provider_name=payload.provider_name,
            model_name=payload.model_name,
            request_id=payload.request_id,
            user_id=payload.user_id,
            project_id=payload.project_id,
            task_id=payload.task_id,
            task_type=payload.task_type,
            status=payload.status.value,
            input_tokens=payload.input_tokens,
            output_tokens=payload.output_tokens,
            total_tokens=payload.total_tokens,
            latency_ms=payload.latency_ms,
            retrieval_hit_count=payload.retrieval_hit_count,
            error_message=payload.error_message,
        )
        # add() 先把实体加入当前 SQLAlchemy Session，commit() 才真正提交。
        self.add(usage_log)
        await self.commit()

    async def get_default_model(self) -> AIModel | None:
        """查询系统默认 AI 模型，并同时加载它的服务商。"""
        statement = select(AIModel).options(selectinload(AIModel.provider)).where(
            AIModel.is_default.is_(True)).order_by(AIModel.id)
        return (await self.session.scalars(statement)).first()

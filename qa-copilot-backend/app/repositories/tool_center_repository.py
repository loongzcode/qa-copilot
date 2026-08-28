"""测试工具中心数据访问层。"""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.models import (
    ExternalConnection,
    FileTemplate,
    ToolApproval,
    ToolArtifact,
    ToolDefinition,
    ToolExecutionLog,
    ToolTask,
)
from app.repositories.base_repository import BaseRepository


class ToolCenterRepository(BaseRepository):
    """封装工具目录、连接、模板、任务和审计记录查询。"""

    async def list_tools(self) -> list[ToolDefinition]:
        return list((await self.session.scalars(select(ToolDefinition).order_by(ToolDefinition.id))).all())

    async def get_tool_by_code(self, code: str) -> ToolDefinition | None:
        return await self.session.scalar(select(ToolDefinition).where(ToolDefinition.code == code))

    async def list_connections(self, project_id: int) -> list[ExternalConnection]:
        return list(
            (
                await self.session.scalars(
                    select(ExternalConnection)
                    .where(ExternalConnection.project_id == project_id)
                    .order_by(ExternalConnection.id.desc())
                )
            ).all()
        )

    async def get_connection(self, project_id: int, connection_id: int) -> ExternalConnection | None:
        return await self.session.scalar(
            select(ExternalConnection).where(
                ExternalConnection.project_id == project_id, ExternalConnection.id == connection_id
            )
        )

    async def has_connection_reference(self, project_id: int, connection_id: int) -> bool:
        """检查任务 JSON 参数是否引用连接，保证审计历史不会悬空。"""
        count = await self.session.scalar(
            select(func.count(ToolTask.id)).where(
                ToolTask.project_id == project_id,
                or_(
                    ToolTask.input_data["source_connection_id"].as_integer() == connection_id,
                    ToolTask.input_data["target_connection_id"].as_integer() == connection_id,
                    ToolTask.input_data["connection_id"].as_integer() == connection_id,
                ),
            )
        )
        return bool(count)

    async def list_templates(self, project_id: int) -> list[FileTemplate]:
        return list(
            (
                await self.session.scalars(
                    select(FileTemplate).where(FileTemplate.project_id == project_id).order_by(FileTemplate.id.desc())
                )
            ).all()
        )

    async def get_template(self, project_id: int, template_id: int) -> FileTemplate | None:
        return await self.session.scalar(
            select(FileTemplate).where(FileTemplate.project_id == project_id, FileTemplate.id == template_id)
        )

    async def list_tasks(
        self, project_id: int, *, status: str | None, task_type: str | None, current: int, size: int
    ) -> tuple[list[ToolTask], int]:
        conditions = [ToolTask.project_id == project_id]
        if status is not None:
            conditions.append(ToolTask.status == status)
        if task_type is not None:
            conditions.append(ToolTask.task_type == task_type)
        total = int(await self.session.scalar(select(func.count(ToolTask.id)).where(*conditions)) or 0)
        statement = (
            select(ToolTask)
            .options(selectinload(ToolTask.tool))
            .where(*conditions)
            .order_by(ToolTask.id.desc())
            .offset((current - 1) * size)
            .limit(size)
        )
        return list((await self.session.scalars(statement)).all()), total

    async def get_task(self, project_id: int, task_id: int, *, lock: bool = False) -> ToolTask | None:
        statement = (
            select(ToolTask)
            .options(selectinload(ToolTask.tool))
            .where(ToolTask.project_id == project_id, ToolTask.id == task_id)
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def list_approvals(self, task_id: int) -> list[ToolApproval]:
        return list(
            (
                await self.session.scalars(
                    select(ToolApproval).where(ToolApproval.task_id == task_id).order_by(ToolApproval.id)
                )
            ).all()
        )

    async def list_logs(self, task_id: int) -> list[ToolExecutionLog]:
        return list(
            (
                await self.session.scalars(
                    select(ToolExecutionLog).where(ToolExecutionLog.task_id == task_id).order_by(ToolExecutionLog.id)
                )
            ).all()
        )

    async def list_artifacts(self, task_id: int) -> list[ToolArtifact]:
        return list(
            (
                await self.session.scalars(
                    select(ToolArtifact).where(ToolArtifact.task_id == task_id).order_by(ToolArtifact.id)
                )
            ).all()
        )

    async def get_artifact(self, task_id: int, artifact_id: int) -> ToolArtifact | None:
        """按任务边界查询产物，防止通过产物 ID 猜测跨任务下载。"""
        return await self.session.scalar(
            select(ToolArtifact).where(
                ToolArtifact.task_id == task_id,
                ToolArtifact.id == artifact_id,
            )
        )

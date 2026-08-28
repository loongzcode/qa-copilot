
from sqlalchemy import func, or_, select

from app.models import PromptTemplate
from app.repositories.base_repository import BaseRepository


class PromptTemplateRepository(BaseRepository):
    async def get_prompt_template(
            self,
            prompt_id: int,
    ) -> PromptTemplate | None:
        prompt_template = await self.session.scalar(
            select(PromptTemplate).where(
                PromptTemplate.id == prompt_id,
            )
        )
        return prompt_template

    async def get_by_code(
            self,
            code: str,
    ) -> PromptTemplate | None:
        prompt_template = await self.session.scalar(
            select(PromptTemplate).where(
                PromptTemplate.code == code,
            )
        )
        return prompt_template

    async def list_templates(
            self,
            keyword: str,
            enabled: bool | None,
            current: int,
            size: int,
    ) -> tuple[list[PromptTemplate], int]:
        conditions = []
        if keyword:
            conditions.append(
                or_(
                    PromptTemplate.name.contains(keyword),
                    PromptTemplate.code.contains(keyword),
                    PromptTemplate.description.contains(keyword),
                )
            )
        if enabled is not None:
            conditions.append(PromptTemplate.enabled == enabled)
        total_statement = (
            select(func.count(PromptTemplate.id))
            .where(*conditions)
        )

        total = await self.session.scalar(total_statement) or 0

        statement = (
            select(PromptTemplate)
            .where(*conditions)
            .order_by(
                PromptTemplate.updated_at.desc(),
                PromptTemplate.id.desc(),
            )
            .offset((current - 1) * size)
            .limit(size)
        )
        templates = list(
            (await self.session.scalars(statement)).all()
        )
        return templates, total


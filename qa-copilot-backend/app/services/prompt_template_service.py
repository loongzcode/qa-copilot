from string import Formatter

from sqlalchemy.exc import IntegrityError

from app.core.constants import (
    BUILT_IN_PROMPT_CODES,
    PROMPT_REQUIRED_VARIABLES,
)
from app.exceptions import BadRequestException, ConflictException, NotFoundException
from app.models import PromptTemplate
from app.repositories.prompt_template_repository import PromptTemplateRepository
from app.schemas.dto.prompt_templates import (
    PromptTemplateCreateDTO,
    PromptTemplatePreviewDTO,
    PromptTemplateUpdateDTO,
    PromptTextPreviewDTO,
)
from app.schemas.vo.prompt_templates import PromptTemplateListVO, PromptTemplatePreviewVO, PromptTemplateVO


class PromptTemplateService:
    def __init__(self, repository: PromptTemplateRepository):
        self.repository = repository

    @staticmethod
    def _prompt_template_list_read(
        prompt: PromptTemplate,
    ) -> PromptTemplateListVO:
        return PromptTemplateListVO(
            id=prompt.id,
            code=prompt.code,
            name=prompt.name,
            description=prompt.description,
            enabled=prompt.enabled,
            created_at=prompt.created_at,
            updated_at=prompt.updated_at,
        )

    @staticmethod
    def _prompt_template_read(
        prompt: PromptTemplate,
    ) -> PromptTemplateVO:
        return PromptTemplateVO(
            id=prompt.id,
            code=prompt.code,
            name=prompt.name,
            description=prompt.description,
            enabled=prompt.enabled,
            created_at=prompt.created_at,
            updated_at=prompt.updated_at,
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt,
        )

    @staticmethod
    def _extract_prompt_variables(prompt_text: str) -> frozenset[str]:
        variables = set()
        try:
            #   ("用户问题：", "question", "", None)
            # Formatter.parse() 方法规定好的返回协议
            # 普通文本 | 字段名 | 格式规则 | 转换规则
            for _, field_name, format_spec, conversion in Formatter().parse(prompt_text):
                if field_name is None:
                    continue
                if not field_name.isidentifier():
                    raise BadRequestException("仅支持 {variable_name} 格式")
                if format_spec or conversion is not None:
                    raise BadRequestException("Prompt 仅支持 {variable_name} 格式的简单占位符")
                variables.add(field_name)
        except ValueError as e:
            raise BadRequestException("Prompt 占位符花括号格式不正确") from e
        return frozenset(variables)

    # 调用_extract_prompt_variables提取变量，然后对比变量是否有缺少或者不合法的
    def _validate_required_variables(
        self,
        code: str,
        system_prompt: str,
        user_prompt: str,
    ) -> None:
        actual_variables = self._extract_prompt_variables(system_prompt) | self._extract_prompt_variables(user_prompt)

        required_variables = PROMPT_REQUIRED_VARIABLES.get(code)
        if required_variables is None:
            return
        missing_variables = required_variables - actual_variables
        unexpected_variables = actual_variables - required_variables
        if missing_variables:
            names = ", ".join(sorted(missing_variables))
            raise BadRequestException(f"Prompt 缺少必需变量：{names}")

        if unexpected_variables:
            names = ", ".join(sorted(unexpected_variables))
            raise BadRequestException(f"Prompt 包含不支持的变量：{names}")

    async def _get_template_or_raise(self, prompt_id: int) -> PromptTemplate:
        prompt = await self.repository.get_prompt_template(prompt_id=prompt_id)
        if prompt is None:
            raise NotFoundException("Prompt 模板不存在")
        return prompt

    async def list_templates(
        self,
        keyword: str,
        enabled: bool | None,
        current: int,
        size: int,
    ) -> tuple[list[PromptTemplateListVO], int]:
        templates, total = await self.repository.list_templates(
            keyword=keyword.strip(), enabled=enabled, current=current, size=size
        )
        records = [self._prompt_template_list_read(template) for template in templates]

        return records, total

    async def get_template(self, prompt_id: int) -> PromptTemplateVO:
        prompt = await self._get_template_or_raise(prompt_id=prompt_id)
        return self._prompt_template_read(prompt)

    async def create_template(self, payload: PromptTemplateCreateDTO) -> PromptTemplateVO:
        existing_prompt = await self.repository.get_by_code(code=payload.code)
        if existing_prompt is not None:
            raise ConflictException("Prompt 模板编码已存在")
        changes = payload.model_dump(exclude_unset=True)
        self._validate_required_variables(
            code=payload.code,
            system_prompt=payload.system_prompt,
            user_prompt=payload.user_prompt,
        )
        prompt = PromptTemplate(**changes)
        self.repository.add(prompt)
        try:
            await self.repository.commit()
        except IntegrityError as e:
            await self.repository.rollback()
            raise ConflictException("Prompt 模板编码已存在") from e
        return self._prompt_template_read(prompt)

    async def update_template(self, prompt_id: int, payload: PromptTemplateUpdateDTO) -> PromptTemplateVO:
        prompt = await self._get_template_or_raise(prompt_id=prompt_id)
        changes = payload.model_dump(exclude_unset=True)
        if changes.get("enabled") is False and prompt.code in BUILT_IN_PROMPT_CODES:
            raise ConflictException("该 Prompt 正在被系统工作流使用，不能停用")
        system_prompt = changes.get(
            "system_prompt",
            prompt.system_prompt,
        )
        user_prompt = changes.get(
            "user_prompt",
            prompt.user_prompt,
        )
        self._validate_required_variables(
            code=prompt.code,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        for key, value in changes.items():
            setattr(prompt, key, value)
        await self.repository.commit()
        return self._prompt_template_read(prompt)

    async def preview_template(self, prompt_id: int, payload: PromptTemplatePreviewDTO) -> PromptTemplatePreviewVO:
        """使用调用方示例变量渲染最终文本，但不产生 AI 调用和费用。"""
        prompt = await self._get_template_or_raise(prompt_id=prompt_id)
        required = self._extract_prompt_variables(prompt.system_prompt) | self._extract_prompt_variables(
            prompt.user_prompt
        )
        missing = required - set(payload.variables)
        if missing:
            raise BadRequestException(f"预览缺少变量：{', '.join(sorted(missing))}")
        values = {name: str(payload.variables[name]) for name in required}
        return PromptTemplatePreviewVO(
            code=prompt.code,
            variables=sorted(required),
            rendered_system_prompt=prompt.system_prompt.format_map(values),
            rendered_user_prompt=prompt.user_prompt.format_map(values),
        )

    def preview_text(self, payload: PromptTextPreviewDTO) -> PromptTemplatePreviewVO:
        """渲染页面当前编辑值，使用户保存前发现变量或排版问题。"""
        self._validate_required_variables(payload.code, payload.system_prompt, payload.user_prompt)
        required = self._extract_prompt_variables(payload.system_prompt) | self._extract_prompt_variables(
            payload.user_prompt
        )
        missing = required - set(payload.variables)
        if missing:
            raise BadRequestException(f"预览缺少变量：{', '.join(sorted(missing))}")
        values = {name: str(payload.variables[name]) for name in required}
        return PromptTemplatePreviewVO(
            code=payload.code,
            variables=sorted(required),
            rendered_system_prompt=payload.system_prompt.format_map(values),
            rendered_user_prompt=payload.user_prompt.format_map(values),
        )

    async def delete_template(self, prompt_id: int) -> None:
        prompt = await self._get_template_or_raise(prompt_id=prompt_id)
        if prompt.code in BUILT_IN_PROMPT_CODES:
            raise ConflictException("系统内置 Prompt 模板不能删除，可以将其停用")
        await self.repository.delete(prompt)
        await self.repository.commit()

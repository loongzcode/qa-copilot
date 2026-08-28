"""Prompt 预览和系统模板保护规则测试。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.exceptions import BadRequestException, ConflictException
from app.schemas.dto.prompt_templates import PromptTemplatePreviewDTO, PromptTemplateUpdateDTO, PromptTextPreviewDTO
from app.services.prompt_template_service import PromptTemplateService


def prompt_template(*, code: str = "rag_answer", enabled: bool = True) -> SimpleNamespace:
    """构造不依赖数据库的最小 Prompt 实体，保证测试只验证业务规则。"""
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=1,
        code=code,
        name="测试模板",
        description="",
        system_prompt="请仅根据下面资料回答：{context}\n历史记忆：{memory}",
        user_prompt="当前问题：{question}",
        enabled=enabled,
        created_at=now,
        updated_at=now,
    )


def test_preview_unsaved_text_renders_all_variables() -> None:
    """保存前预览应替换变量，同时返回实际使用的变量清单。"""
    service = PromptTemplateService(repository=SimpleNamespace())

    result = service.preview_text(
        PromptTextPreviewDTO(
            code="custom_prompt",
            system_prompt="项目：{project}",
            user_prompt="问题：{question}",
            variables={"project": "LBlog", "question": "如何发布文章？"},
        )
    )

    assert result.variables == ["project", "question"]
    assert result.rendered_system_prompt == "项目：LBlog"
    assert result.rendered_user_prompt == "问题：如何发布文章？"


def test_preview_rejects_missing_variable() -> None:
    """缺少运行变量时必须拒绝预览，避免真正调用模型时才发现模板不可用。"""
    service = PromptTemplateService(repository=SimpleNamespace())

    with pytest.raises(BadRequestException, match="预览缺少变量"):
        service.preview_text(
            PromptTextPreviewDTO(
                code="custom_prompt",
                system_prompt="项目：{project}",
                user_prompt="问题：{question}",
                variables={"project": "LBlog"},
            )
        )


@pytest.mark.asyncio
async def test_saved_template_preview_and_built_in_disable_protection() -> None:
    """已保存模板可预览，但系统工作流使用的内置模板不能被停用。"""
    repository = SimpleNamespace(
        get_prompt_template=AsyncMock(return_value=prompt_template()),
        commit=AsyncMock(),
    )
    service = PromptTemplateService(repository=repository)

    preview = await service.preview_template(
        1,
        PromptTemplatePreviewDTO(
            variables={"context": "资料", "memory": "无", "question": "问题"}
        ),
    )
    assert preview.rendered_user_prompt == "当前问题：问题"

    with pytest.raises(ConflictException, match="不能停用"):
        await service.update_template(1, PromptTemplateUpdateDTO(enabled=False))
    repository.commit.assert_not_awaited()

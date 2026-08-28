from datetime import datetime

from app.schemas.camel_model import CamelModel


class PromptTemplateListVO(CamelModel):
    # 写列表字段
    id: int
    code: str
    name: str
    description: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class PromptTemplateVO(PromptTemplateListVO):
    """返回给 Prompt 管理页面的完整模板信息。"""

    # 只写完整 Prompt 字段
    system_prompt: str
    user_prompt: str


class PromptTemplatePreviewVO(CamelModel):
    """替换变量后的最终 System/User Prompt。"""

    code: str
    variables: list[str]
    rendered_system_prompt: str
    rendered_user_prompt: str

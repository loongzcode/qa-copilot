from typing import Any

from pydantic import Field, field_validator, model_validator

from app.core.constants import RequirementItemType, TestAssetPriority
from app.schemas.camel_model import CamelModel


class RequirementCreateDTO(CamelModel):
    """创建一条需求业务记录；project_id 由接口路径提供。"""

    module_id: int | None = Field(default=None, gt=0, description="可选的所属功能模块 ID")
    document_id: int | None = Field(default=None, gt=0, description="可选的原始知识文档 ID")
    title: str = Field(min_length=1, max_length=300, description="需求标题")
    version: str = Field(default="1.0", min_length=1, max_length=40, description="需求版本标识")
    source_url: str | None = Field(default=None, max_length=1000, description="可选的外部需求地址")
    summary: str = Field(default="", max_length=20000, description="需求摘要或补充说明")
    metadata: dict[str, Any] = Field(default_factory=dict, description="需求扩展信息")

    @field_validator("title", "version", "source_url", "summary", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        """去掉用户输入两侧的空格，避免保存只有空格的标题。"""

        return value.strip() if isinstance(value, str) else value


class RequirementUpdateDTO(CamelModel):
    """编辑需求元数据；只更新前端实际传入的字段。"""

    module_id: int | None = Field(default=None, gt=0)
    document_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    version: str | None = Field(default=None, min_length=1, max_length=40)
    source_url: str | None = Field(default=None, max_length=1000)
    summary: str | None = Field(default=None, max_length=20000)
    metadata: dict[str, Any] | None = None

    @field_validator("title", "version", "source_url", "summary", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> RequirementUpdateDTO:
        """可选关联允许清空，但标题和版本不能被显式改为 null。"""

        for field_name in ("title", "version", "summary", "metadata"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} 不能设置为空")
        return self


class RequirementExtractionSubmitDTO(CamelModel):
    """提交需求拆解任务时可调整的执行选项。"""

    replace_unconfirmed_ai_items: bool = Field(
        default=True,
        description="是否替换上一次生成且尚未人工确认的 AI 需求点",
    )


class RequirementItemCreateDTO(CamelModel):
    """测试人员手工补充一条原子需求点。"""

    parent_id: int | None = Field(default=None, gt=0)
    item_code: str | None = Field(default=None, min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=10000)
    item_type: RequirementItemType = RequirementItemType.FUNCTIONAL
    priority: TestAssetPriority = TestAssetPriority.P2
    acceptance_criteria: str = Field(default="", max_length=10000)
    source_locator: dict[str, Any] = Field(default_factory=dict)
    order_no: int = Field(default=0, ge=0)

    @field_validator("item_code", "title", "description", "acceptance_criteria", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class RequirementItemUpdateDTO(CamelModel):
    """人工校正需求点；字段不传表示保持原值。"""

    parent_id: int | None = Field(default=None, gt=0)
    item_code: str | None = Field(default=None, min_length=1, max_length=80)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    item_type: RequirementItemType | None = None
    priority: TestAssetPriority | None = None
    acceptance_criteria: str | None = Field(default=None, max_length=10000)
    source_locator: dict[str, Any] | None = None
    order_no: int | None = Field(default=None, ge=0)

    @field_validator("item_code", "title", "description", "acceptance_criteria", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> RequirementItemUpdateDTO:
        """可清空父级和编码，但数据库非空字段不能被显式更新成 null。"""

        required_fields = (
            "title",
            "description",
            "item_type",
            "priority",
            "acceptance_criteria",
            "source_locator",
            "order_no",
        )
        for field_name in required_fields:
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} 不能设置为空")
        return self


class RequirementItemsConfirmDTO(CamelModel):
    """批量确认需求点，避免前端为每条需求点单独发送一次请求。"""

    item_ids: list[int] = Field(min_length=1, max_length=500)

    @field_validator("item_ids")
    @classmethod
    def deduplicate_ids(cls, value: list[int]) -> list[int]:
        """保持原顺序去重，同时拒绝非法 ID。"""

        if any(item_id <= 0 for item_id in value):
            raise ValueError("需求点 ID 必须大于 0")
        return list(dict.fromkeys(value))

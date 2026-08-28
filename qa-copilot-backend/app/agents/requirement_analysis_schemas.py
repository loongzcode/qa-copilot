"""需求分析工作流使用的 AI 结构化输出模型。

这里的模型不是前端 DTO/VO，也不是数据库实体。它们只负责约束大模型返回的
JSON，确保结构完整、父子关系合法后，Service 才把需求点写入数据库。
"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.constants import RequirementItemType, TestAssetPriority


class ExtractedRequirementItem(BaseModel):
    """AI 从需求原文中拆出的一条、尚未保存到数据库的原子需求点。"""

    # 拒绝模型临时发明的未知字段，避免错误字段被 Pydantic 悄悄忽略。
    model_config = ConfigDict(extra="forbid")

    # AI 输出中的临时编号，例如 REQ-1。数据库记录尚未创建，因此不能使用
    # requirement_items.id；保存阶段会通过该编号解析父子关系。
    local_id: str = Field(min_length=1, max_length=80)
    # 父需求点的临时编号。它与 local_id 类型相同；顶层需求点允许为 None。
    parent_local_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
    )
    # 标题、说明和验收条件是人工审核与用例生成的基础，不能缺失或全是空格。
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=10_000)
    item_type: RequirementItemType
    priority: TestAssetPriority
    acceptance_criteria: str = Field(min_length=1, max_length=10_000)
    # 文档来源时返回支撑结论的切片 ID；摘要来源没有切片，允许空列表。
    source_chunk_ids: list[int] = Field(default_factory=list, max_length=100)
    # 保留一小段原文证据方便人工审核；真实归属仍要由 Service 根据切片 ID 校验。
    source_quote: str = Field(default="", max_length=2_000)

    @field_validator(
        "local_id",
        "parent_local_id",
        "title",
        "description",
        "acceptance_criteria",
        "source_quote",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: object) -> object:
        """去掉文本两侧空格，再由 Field 检查长度。

        parent_local_id 可以为 None，所以这里只处理字符串。标题如果只有空格，
        strip 后会变成空字符串，随后触发 min_length=1。
        """

        return value.strip() if isinstance(value, str) else value

    @field_validator("source_chunk_ids")
    @classmethod
    def validate_source_chunk_ids(cls, value: list[int]) -> list[int]:
        """拒绝非法切片 ID，并在不打乱顺序的前提下去重。"""

        if any(chunk_id <= 0 for chunk_id in value):
            raise ValueError("来源切片 ID 必须大于 0")
        # dict.fromkeys([8, 3, 8]) 得到 [8, 3]，set 则可能打乱原顺序。
        return list(dict.fromkeys(value))


class RequirementExtractionOutput(BaseModel):
    """一次模型调用返回的全部需求点、警告和分析摘要。"""

    model_config = ConfigDict(extra="forbid")

    # 至少产生一条需求点；上限用于防止异常模型响应一次写入过多数据。
    items: list[ExtractedRequirementItem] = Field(min_length=1, max_length=200)
    # 歧义、缺失条件和冲突可能有多条，所以使用列表而不是单个字符串。
    warnings: list[str] = Field(default_factory=list, max_length=100)
    analysis_summary: str = Field(default="", max_length=2_000)

    @field_validator("warnings")
    @classmethod
    def clean_warnings(cls, value: list[str]) -> list[str]:
        """删除空警告并保持原顺序去重，避免前端展示重复提示。"""

        cleaned = [warning.strip() for warning in value if warning.strip()]
        return list(dict.fromkeys(cleaned))

    @field_validator("analysis_summary", mode="before")
    @classmethod
    def strip_analysis_summary(cls, value: object) -> object:
        """去除分析摘要两侧无意义的空格。"""

        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_item_relationships(self) -> Self:
        """校验整个 items 列表中的编号和父子关系。

        单条需求点只能验证自己的字段；编号是否重复、父编号是否存在和是否形成
        环，必须拿到完整列表后判断，因此使用 model_validator(after)。
        """

        # list 保留原顺序，set 用于快速判断编号是否存在。
        local_ids = [item.local_id for item in self.items]
        known_ids = set(local_ids)

        # set 会去掉重复值；去重后数量变少，说明 AI 返回了重复编号。
        if len(known_ids) != len(local_ids):
            raise ValueError("AI 返回的需求点临时编号不能重复")

        # 建立“当前编号 -> 父编号”映射，循环检测会沿父级逐层向上查询。
        parent_map = {
            item.local_id: item.parent_local_id
            for item in self.items
        }

        for item in self.items:
            parent_local_id = item.parent_local_id
            # None 表示顶层需求点，不需要继续校验父级。
            if parent_local_id is None:
                continue
            if parent_local_id == item.local_id:
                raise ValueError(
                    f"需求点 {item.local_id} 不能把自己设置为父级"
                )
            if parent_local_id not in known_ids:
                raise ValueError(
                    f"需求点 {item.local_id} 引用了不存在的父编号 "
                    f"{parent_local_id}"
                )

        # 从每个需求点出发沿父级向上查。正常结构最终走到 None；如果再次遇到
        # 同一路径中访问过的编号，就说明形成了循环。
        for start_id in local_ids:
            current_id: str | None = start_id
            visited: set[str] = set()

            while current_id is not None:
                if current_id in visited:
                    raise ValueError(
                        f"需求点父子关系存在循环，涉及编号 {current_id}"
                    )
                visited.add(current_id)
                current_id = parent_map[current_id]

        # after 模式必须返回校验后的模型本身。
        return self


"""知识问答会话、消息和记忆管理响应模型。"""
from datetime import datetime

from app.core.constants import (
    KnowledgeChatMemoryStatus,
    KnowledgeChatMessageRole,
    KnowledgeChatMessageStatus,
    KnowledgeChatSessionStatus,
    KnowledgeChatStreamStage,
)
from app.schemas.camel_model import CamelModel
from app.schemas.vo.knowledge_bases import KnowledgeSearchResultVO
from pydantic import Field


class KnowledgeCitationVO(KnowledgeSearchResultVO):
    """大模型回答引用的一条知识来源。"""

    source_number: int = Field(
        ge=1,
        description="本次回答中的资料编号",
    )


class KnowledgeChatSessionVO(CamelModel):
    """
    用于返回会话列表和创建会话结果
    """
    id: int
    project_id: int
    knowledge_base_id: int
    user_id: int
    # 审计列表用于识别会话创建人；普通用户会话接口也可安全返回该公开账号名。
    user_name: str | None = None
    title: str
    status: KnowledgeChatSessionStatus
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


class KnowledgeChatMessageVO(CamelModel):
    """
    加载历史消息
    返回刚保存的用户消息
    返回 AI 回答及其引用
    展示生成失败状态
    """
    id: int
    session_id: int
    role: KnowledgeChatMessageRole
    content: str
    citations: list[KnowledgeCitationVO] = Field(default_factory=list)
    model_id: int | None
    prompt_template_id: int | None
    status: KnowledgeChatMessageStatus
    token_count: int
    error_message: str | None
    created_at: datetime


class KnowledgeChatMessageCursorVO(CamelModel):
    """
    游标分页 VO：
    records       当前批次消息
    has_more      是否还有更早的消息
    next_cursor   下次查询使用的 before_id
    """
    records: list[KnowledgeChatMessageVO] = Field(default_factory=list)
    has_more: bool
    next_cursor: int | None


class KnowledgeChatSendResultVO(CamelModel):
    """发送问题后返回已持久化的用户消息和 AI 消息。
        记录返回的用户信息和AI信息
    user_message 来自用户提问
    assistant_message 来自AI返回的消息
    发送问题成功后，为什么返回用户消息和 AI 消息两条记录？
        让前端取得两条消息真实的数据库 ID 和时间
    """

    # 用户消息也需要返回，前端才能取得它真实的数据库 ID 和创建时间。
    user_message: KnowledgeChatMessageVO
    assistant_message: KnowledgeChatMessageVO


class KnowledgeChatMemorySummaryVO(CamelModel):
    """
    主要用于管理员排查记忆压缩任务
    摘要详情可以告诉管理员:
        压缩了哪段消息
        使用了什么模型
        摘要内容是什么
        Token 数是多少
        任务是否失败
    """
    id: int
    session_id: int
    from_message_id: int
    to_message_id: int
    message_count: int
    summary: str
    token_count: int
    model_id: int | None
    status: KnowledgeChatMemoryStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime

class KnowledgeChatStreamStatusVO(CamelModel):
    """流式问答当前执行阶段。"""

    # 固定的阶段编码，前端可以根据它选择图标和显示状态。
    stage: KnowledgeChatStreamStage

    # 直接展示给用户的中文说明，例如“正在检索知识库”。
    message: str


class KnowledgeChatStreamDeltaVO(CamelModel):
    """大模型本次新生成的一小段回答。"""

    # 这里只保存新增文字，不是截至当前的完整回答。
    # 前端会不断把多个 content 拼接成完整回答。
    content: str


class KnowledgeChatStreamCitationsVO(CamelModel):
    """大模型回答引用的知识来源。"""

    # 回答生成完成后，前端使用它展示引用资料卡片。
    citations: list[KnowledgeCitationVO] = Field(
        default_factory=list
    )


class KnowledgeChatStreamErrorVO(CamelModel):
    """流式问答执行失败事件。"""

    # 展示给用户的失败原因。
    message: str

    # 后端已经把占位消息更新为 FAILED 时，返回数据库中的真实消息。
    # 如果异常发生得太早，还没有取得消息，则允许为 None。
    assistant_message: KnowledgeChatMessageVO | None = None

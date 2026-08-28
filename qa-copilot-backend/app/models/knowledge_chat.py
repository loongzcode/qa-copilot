from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.ai_model import AIModel
    from app.models.knowledge_bases import KnowledgeBase
    from app.models.prompt_template import PromptTemplate
    from app.models.test_projects import TestProjects
    from app.models.user import User


class KnowledgeChatSession(TimestampMixin, Base):
    """一次独立的知识问答会话，也是权限和记忆隔离边界。

    TimestampMixin 还会提供 created_at 和 updated_at：前者记录会话创建时间，
    后者记录会话标题、状态或记忆游标最后一次发生变化的时间。
    """

    __tablename__ = "knowledge_chat_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED')",
            name="chk_knowledge_chat_sessions_status",
        ),
        CheckConstraint(
            "unsummarized_token_count >= 0",
            name="chk_knowledge_chat_sessions_unsummarized_tokens",
        ),
        CheckConstraint(
            "memory_version >= 0",
            name="chk_knowledge_chat_sessions_memory_version",
        ),
        Index(
            "ix_knowledge_chat_sessions_user_last_message",
            "user_id",
            "last_message_at",
        ),
        Index(
            "ix_knowledge_chat_sessions_scope",
            "project_id",
            "knowledge_base_id",
            "user_id",
            "status",
        ),
        {"comment": "知识问答会话，作为用户对话、权限和记忆隔离边界"},
    )

    # 会话主键。使用 BIGINT 是因为长期运行后会话数量可能很大，同时它也是
    # 前端切换会话、查询消息和提交问题时使用的 session_id。
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        comment="会话主键",
    )
    # 会话所属测试项目。项目被物理删除时会级联删除它的会话，防止留下
    # 已经失去业务归属的孤立聊天记录。
    project_id: Mapped[int] = mapped_column(
        ForeignKey("test_projects.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属测试项目 ID",
    )
    # 本会话固定使用的知识库。发送每个问题时都在这个知识库内检索，避免
    # 同一会话前后切换知识库后造成引用范围混乱。
    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        comment="本会话固定使用的知识库 ID",
    )
    # 会话创建人，也是普通用户访问会话时的数据权限条件。它必须取自
    # current_user.id，不能接受前端自行指定。
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="会话创建用户 ID，也是普通用户的数据权限条件",
    )
    # 会话列表中展示的标题。创建时可以先使用“新会话”，之后可根据第一条
    # 用户问题自动生成，也允许用户手动重命名。
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="新会话",
        server_default=text("'新会话'"),
        comment="会话标题，首次提问后可自动生成并允许用户修改",
    )
    # 会话状态：ACTIVE 表示正常使用，ARCHIVED 表示保留历史但从默认活跃
    # 列表中隐藏。状态合法值统一由 KnowledgeChatSessionStatus 管理。
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACTIVE",
        server_default=text("'ACTIVE'"),
        comment="会话状态：ACTIVE 活跃，ARCHIVED 已归档",
    )
    # 最近一条消息的创建时间。会话列表按它倒序排列，让最近交流的会话
    # 显示在最前面；新建但尚未发送消息时允许为 None。
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最近一条消息的创建时间，用于会话列表排序",
    )
    # 从 last_summarized_message_id 之后，尚未被压缩进摘要的消息 Token 总数。
    # 每次保存消息时累加，达到阈值后用于触发 Celery 记忆压缩任务。
    unsummarized_token_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="从摘要位置之后尚未压缩的原始消息 Token 总数",
    )
    # 最后一条已经进入摘要的消息 ID。下次压缩只处理它之后的旧消息，避免
    # 重复摘要。这里只保存游标，不建立指向消息表的循环外键；业务层会保证
    # 该消息属于当前会话。尚未产生任何摘要时为 None。
    last_summarized_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="最后一条已经写入长期摘要的消息 ID",
    )
    # 当前会话记忆的版本号。Worker 每成功生成一段摘要就递增；任务启动时
    # 记录旧版本，提交前再次比较，可防止两个并发任务重复压缩同一段消息。
    memory_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="会话记忆版本，每成功完成一次压缩加一",
    )
    # 软删除时间。None 表示会话仍有效；有值表示用户已删除。先软删除便于
    # 审计和误删恢复，后续保留策略到期后再进行物理清理。
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="软删除时间，NULL 表示未删除",
    )

    # project_id 对应的项目关系对象，供 Service 做项目名称展示和权限校验；
    # 它不是 knowledge_chat_sessions 表中的额外字段。
    project: Mapped[TestProjects] = relationship(
        "TestProjects",
        foreign_keys=[project_id],
        lazy="selectin",
    )
    # knowledge_base_id 对应的知识库关系对象，用于检查知识库启用状态、
    # 可见范围以及取得 Embedding/Rerank 配置。
    knowledge_base: Mapped[KnowledgeBase] = relationship(
        "KnowledgeBase",
        foreign_keys=[knowledge_base_id],
        lazy="selectin",
    )
    # user_id 对应的会话创建人关系对象，用于展示创建人和执行所有权校验。
    user: Mapped[User] = relationship(
        "User",
        foreign_keys=[user_id],
        lazy="selectin",
    )
    # 会话拥有的全部原始消息关系。删除会话时 ORM/数据库会级联删除消息；
    # 列表接口不会直接访问这里加载全部消息，而是通过 Repository 游标分页。
    messages: Mapped[list[KnowledgeChatMessage]] = relationship(
        "KnowledgeChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # 会话的版本化记忆摘要关系。每条摘要覆盖一个消息区间；删除会话时
    # 摘要及其向量也随之级联删除。
    memory_summaries: Mapped[list[KnowledgeChatMemorySummary]] = relationship(
        "KnowledgeChatMemorySummary",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class KnowledgeChatMessage(Base):
    """会话中的一条原始消息；压缩记忆不会替代或删除原始消息。"""

    __tablename__ = "knowledge_chat_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('USER', 'ASSISTANT')",
            name="chk_knowledge_chat_messages_role",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'SUCCESS', 'FAILED')",
            name="chk_knowledge_chat_messages_status",
        ),
        CheckConstraint(
            "token_count >= 0",
            name="chk_knowledge_chat_messages_token_count",
        ),
        # PostgreSQL 的 B-tree 可以反向扫描，因此该复合索引同时支持
        # ORDER BY id DESC LIMIT n 和 id < before_id 的游标分页。
        Index("ix_knowledge_chat_messages_session_id", "session_id", "id"),
        {"comment": "知识问答会话的原始消息时间线"},
    )

    # 消息主键，同时作为稳定的游标。使用 id < before_id 查询更早消息，
    # 避免长会话使用 OFFSET 时越翻越慢。
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        comment="消息主键，同时作为游标分页的稳定游标",
    )
    # 消息所属会话。会话被物理删除时消息级联删除，保证不会留下孤立消息。
    session_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属知识问答会话 ID",
    )
    # 消息发送方：USER 表示用户问题，ASSISTANT 表示 AI 回答。这里不保存
    # System Prompt；系统提示词通过 prompt_template_id 单独追溯。
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="消息角色：USER 用户，ASSISTANT AI 助手",
    )
    # 消息正文原文。用户问题和最终 AI 回答都完整保存，摘要不会覆盖它。
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="用户问题或 AI 回答的正文原文",
    )
    # AI 回答当时使用的引用快照，保存文档、切片、页码、资料编号和分数等。
    # 用户消息通常保存空列表。使用快照可以避免文档重建后历史引用发生变化。
    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
        comment="AI 回答使用的知识库引用快照，用户消息通常为空数组",
    )
    # 生成这条 AI 回答的模型主键。用户消息没有模型，因此允许为 None；
    # 模型配置被删除时使用 SET NULL，历史消息正文仍然保留。
    model_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_models.id", ondelete="SET NULL"),
        nullable=True,
        comment="生成 AI 回答所使用的模型 ID，用户消息为空",
    )
    # 生成这条回答时使用的 Prompt 模板主键，用于审计回答来自哪个模板。
    # 用户消息不使用 Prompt；模板被删除时同样只置空，不删除历史消息。
    prompt_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"),
        nullable=True,
        comment="生成 AI 回答所使用的 Prompt 模板 ID",
    )
    # 消息处理状态：PENDING 表示正在生成，SUCCESS 表示生成完成，FAILED
    # 表示生成失败。用户消息正常写入后直接使用 SUCCESS。
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="SUCCESS",
        server_default=text("'SUCCESS'"),
        comment="处理状态：PENDING 生成中，SUCCESS 成功，FAILED 失败",
    )
    # 这条消息正文估算或实际占用的 Token 数，用于累计会话上下文预算和
    # 判断何时触发历史压缩；它不是一次 AI 调用的 input/output Token 统计。
    token_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="消息正文 Token 数，用于上下文预算和记忆压缩触发",
    )
    # AI 回答失败时保存经过截断和脱敏的错误摘要；成功消息和用户消息为 None。
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="AI 回答失败时保存的错误摘要",
    )
    # 消息创建时间，用于前端时间线展示；同一时间下仍以 id 保证稳定顺序。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="消息创建时间",
    )

    # session_id 对应的会话关系对象，不是消息表中的额外数据库字段。
    session: Mapped[KnowledgeChatSession] = relationship(
        "KnowledgeChatSession",
        back_populates="messages",
        foreign_keys=[session_id],
    )
    # model_id 对应的模型关系对象，用于详情页展示模型名称和服务商。
    model: Mapped[AIModel | None] = relationship(
        "AIModel",
        foreign_keys=[model_id],
        lazy="selectin",
    )
    # prompt_template_id 对应的模板关系对象，用于审计和问题排查。
    prompt_template: Mapped[PromptTemplate | None] = relationship(
        "PromptTemplate",
        foreign_keys=[prompt_template_id],
        lazy="selectin",
    )


class KnowledgeChatMemorySummary(TimestampMixin, Base):
    """一段历史消息的版本化摘要及其语义检索向量。

    TimestampMixin 提供 created_at 和 updated_at：分别表示摘要任务记录的
    创建时间，以及摘要状态、正文、向量或失败原因最后一次更新的时间。
    """

    __tablename__ = "knowledge_chat_memory_summaries"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "from_message_id",
            "to_message_id",
            name="uq_knowledge_chat_memory_range",
        ),
        CheckConstraint(
            "from_message_id <= to_message_id",
            name="chk_knowledge_chat_memory_message_range",
        ),
        CheckConstraint(
            "message_count > 0",
            name="chk_knowledge_chat_memory_message_count",
        ),
        CheckConstraint(
            "token_count >= 0",
            name="chk_knowledge_chat_memory_token_count",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'READY', 'FAILED')",
            name="chk_knowledge_chat_memory_status",
        ),
        Index(
            "ix_knowledge_chat_memory_session_range",
            "session_id",
            "to_message_id",
        ),
        Index(
            "ix_knowledge_chat_memory_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        {"comment": "知识问答会话的版本化长期记忆摘要及语义向量"},
    )

    # 摘要记录主键。一段会话可以产生多条摘要，每条负责一个消息区间。
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        comment="长期记忆摘要主键",
    )
    # 摘要所属会话，也是语义检索时必须使用的隔离条件。删除会话时摘要
    # 和对应向量会级联删除。
    session_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属知识问答会话 ID，也是记忆检索隔离条件",
    )
    # 本摘要覆盖的第一条原始消息 ID，和 to_message_id 一起形成可审计区间。
    from_message_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="本摘要覆盖的第一条原始消息 ID",
    )
    # 本摘要覆盖的最后一条原始消息 ID。成功后会话摘要游标推进到这里。
    to_message_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="本摘要覆盖的最后一条原始消息 ID",
    )
    # 本摘要实际压缩了多少条原始消息，用于核对区间完整性和监控压缩效果。
    message_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="本摘要压缩的原始消息数量",
    )
    # 模型生成的摘要正文。它用于问题改写和上下文构建，但不替代原始消息。
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="模型生成的长期记忆摘要正文",
    )
    # 摘要正文自身的 Token 数，用于把相关摘要加入 Prompt 时执行预算控制。
    token_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="摘要正文自身的 Token 数，用于上下文预算",
    )
    # 生成摘要正文的聊天模型主键。模型删除时置空，但摘要和原始消息保留。
    model_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_models.id", ondelete="SET NULL"),
        nullable=True,
        comment="生成摘要正文所使用的聊天模型 ID",
    )
    # 摘要的 1536 维语义向量。用户提出新问题时，可以在当前 session_id
    # 范围内检索与问题最相关的历史摘要；任务尚未向量化或失败时允许为空。
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536),
        nullable=True,
        comment="摘要正文的 1536 维语义向量，用于相关记忆检索",
    )
    # 摘要任务状态：PENDING 表示待生成/向量化，READY 表示可以参与记忆
    # 检索，FAILED 表示任务失败并等待重试。
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default=text("'PENDING'"),
        comment="摘要状态：PENDING 处理中，READY 可检索，FAILED 失败",
    )
    # 摘要或 Embedding 失败时保存经过截断和脱敏的错误摘要；成功时为 None。
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="摘要生成或向量化失败时保存的错误摘要",
    )

    # session_id 对应的会话关系对象，用于权限隔离和摘要游标更新。
    session: Mapped[KnowledgeChatSession] = relationship(
        "KnowledgeChatSession",
        back_populates="memory_summaries",
        foreign_keys=[session_id],
    )
    # model_id 对应的模型关系对象，用于审计摘要由哪个模型生成。
    model: Mapped[AIModel | None] = relationship(
        "AIModel",
        foreign_keys=[model_id],
        lazy="selectin",
    )

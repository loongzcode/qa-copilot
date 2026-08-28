BEGIN;

CREATE TABLE IF NOT EXISTS knowledge_chat_sessions (
    id BIGSERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES test_projects (id) ON DELETE CASCADE,
    knowledge_base_id INTEGER NOT NULL REFERENCES knowledge_bases (id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL DEFAULT '新会话',
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    last_message_at TIMESTAMP WITH TIME ZONE,
    unsummarized_token_count INTEGER NOT NULL DEFAULT 0,
    last_summarized_message_id BIGINT,
    memory_version INTEGER NOT NULL DEFAULT 0,
    deleted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_knowledge_chat_sessions_status
        CHECK (status IN ('ACTIVE', 'ARCHIVED')),
    CONSTRAINT chk_knowledge_chat_sessions_unsummarized_tokens
        CHECK (unsummarized_token_count >= 0),
    CONSTRAINT chk_knowledge_chat_sessions_memory_version
        CHECK (memory_version >= 0)
);

CREATE INDEX IF NOT EXISTS ix_knowledge_chat_sessions_user_last_message
    ON knowledge_chat_sessions (user_id, last_message_at DESC);
CREATE INDEX IF NOT EXISTS ix_knowledge_chat_sessions_scope
    ON knowledge_chat_sessions (project_id, knowledge_base_id, user_id, status);

COMMENT ON TABLE knowledge_chat_sessions IS '知识问答会话，作为用户对话、权限和记忆隔离边界';
COMMENT ON COLUMN knowledge_chat_sessions.id IS '会话主键';
COMMENT ON COLUMN knowledge_chat_sessions.project_id IS '所属测试项目 ID';
COMMENT ON COLUMN knowledge_chat_sessions.knowledge_base_id IS '本会话固定使用的知识库 ID';
COMMENT ON COLUMN knowledge_chat_sessions.user_id IS '会话创建用户 ID，也是普通用户的数据权限条件';
COMMENT ON COLUMN knowledge_chat_sessions.title IS '会话标题，首次提问后可自动生成并允许用户修改';
COMMENT ON COLUMN knowledge_chat_sessions.status IS '会话状态：ACTIVE 活跃，ARCHIVED 已归档';
COMMENT ON COLUMN knowledge_chat_sessions.last_message_at IS '最近一条消息的创建时间，用于会话列表排序';
COMMENT ON COLUMN knowledge_chat_sessions.unsummarized_token_count IS '从摘要位置之后尚未压缩的原始消息 Token 总数';
COMMENT ON COLUMN knowledge_chat_sessions.last_summarized_message_id IS '最后一条已经写入长期摘要的消息 ID';
COMMENT ON COLUMN knowledge_chat_sessions.memory_version IS '会话记忆版本，每成功完成一次压缩加一';
COMMENT ON COLUMN knowledge_chat_sessions.deleted_at IS '软删除时间，NULL 表示未删除';
COMMENT ON COLUMN knowledge_chat_sessions.created_at IS '创建时间';
COMMENT ON COLUMN knowledge_chat_sessions.updated_at IS '更新时间';

CREATE TABLE IF NOT EXISTS knowledge_chat_messages (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES knowledge_chat_sessions (id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_id INTEGER REFERENCES ai_models (id) ON DELETE SET NULL,
    prompt_template_id INTEGER REFERENCES prompt_templates (id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'SUCCESS',
    token_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_knowledge_chat_messages_role
        CHECK (role IN ('USER', 'ASSISTANT')),
    CONSTRAINT chk_knowledge_chat_messages_status
        CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED')),
    CONSTRAINT chk_knowledge_chat_messages_token_count
        CHECK (token_count >= 0)
);

CREATE INDEX IF NOT EXISTS ix_knowledge_chat_messages_session_id
    ON knowledge_chat_messages (session_id, id DESC);

COMMENT ON TABLE knowledge_chat_messages IS '知识问答会话的原始消息时间线';
COMMENT ON COLUMN knowledge_chat_messages.id IS '消息主键，同时作为游标分页的稳定游标';
COMMENT ON COLUMN knowledge_chat_messages.session_id IS '所属知识问答会话 ID';
COMMENT ON COLUMN knowledge_chat_messages.role IS '消息角色：USER 用户，ASSISTANT AI 助手';
COMMENT ON COLUMN knowledge_chat_messages.content IS '用户问题或 AI 回答的正文原文';
COMMENT ON COLUMN knowledge_chat_messages.citations IS 'AI 回答使用的知识库引用快照，用户消息通常为空数组';
COMMENT ON COLUMN knowledge_chat_messages.model_id IS '生成 AI 回答所使用的模型 ID，用户消息为空';
COMMENT ON COLUMN knowledge_chat_messages.prompt_template_id IS '生成 AI 回答所使用的 Prompt 模板 ID';
COMMENT ON COLUMN knowledge_chat_messages.status IS '处理状态：PENDING 生成中，SUCCESS 成功，FAILED 失败';
COMMENT ON COLUMN knowledge_chat_messages.token_count IS '消息正文 Token 数，用于上下文预算和记忆压缩触发';
COMMENT ON COLUMN knowledge_chat_messages.error_message IS 'AI 回答失败时保存的错误摘要';
COMMENT ON COLUMN knowledge_chat_messages.created_at IS '消息创建时间';

CREATE TABLE IF NOT EXISTS knowledge_chat_memory_summaries (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES knowledge_chat_sessions (id) ON DELETE CASCADE,
    from_message_id BIGINT NOT NULL,
    to_message_id BIGINT NOT NULL,
    message_count INTEGER NOT NULL,
    summary TEXT NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0,
    model_id INTEGER REFERENCES ai_models (id) ON DELETE SET NULL,
    embedding vector(1536),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_knowledge_chat_memory_range
        UNIQUE (session_id, from_message_id, to_message_id),
    CONSTRAINT chk_knowledge_chat_memory_message_range
        CHECK (from_message_id <= to_message_id),
    CONSTRAINT chk_knowledge_chat_memory_message_count
        CHECK (message_count > 0),
    CONSTRAINT chk_knowledge_chat_memory_token_count
        CHECK (token_count >= 0),
    CONSTRAINT chk_knowledge_chat_memory_status
        CHECK (status IN ('PENDING', 'READY', 'FAILED'))
);

CREATE INDEX IF NOT EXISTS ix_knowledge_chat_memory_session_range
    ON knowledge_chat_memory_summaries (session_id, to_message_id DESC);
CREATE INDEX IF NOT EXISTS ix_knowledge_chat_memory_embedding
    ON knowledge_chat_memory_summaries
    USING hnsw (embedding vector_cosine_ops);

COMMENT ON TABLE knowledge_chat_memory_summaries IS '知识问答会话的版本化长期记忆摘要及语义向量';
COMMENT ON COLUMN knowledge_chat_memory_summaries.id IS '长期记忆摘要主键';
COMMENT ON COLUMN knowledge_chat_memory_summaries.session_id IS '所属知识问答会话 ID，也是记忆检索隔离条件';
COMMENT ON COLUMN knowledge_chat_memory_summaries.from_message_id IS '本摘要覆盖的第一条原始消息 ID';
COMMENT ON COLUMN knowledge_chat_memory_summaries.to_message_id IS '本摘要覆盖的最后一条原始消息 ID';
COMMENT ON COLUMN knowledge_chat_memory_summaries.message_count IS '本摘要压缩的原始消息数量';
COMMENT ON COLUMN knowledge_chat_memory_summaries.summary IS '模型生成的长期记忆摘要正文';
COMMENT ON COLUMN knowledge_chat_memory_summaries.token_count IS '摘要正文自身的 Token 数，用于上下文预算';
COMMENT ON COLUMN knowledge_chat_memory_summaries.model_id IS '生成摘要正文所使用的聊天模型 ID';
COMMENT ON COLUMN knowledge_chat_memory_summaries.embedding IS '摘要正文的 1536 维语义向量，用于相关记忆检索';
COMMENT ON COLUMN knowledge_chat_memory_summaries.status IS '摘要状态：PENDING 处理中，READY 可检索，FAILED 失败';
COMMENT ON COLUMN knowledge_chat_memory_summaries.error_message IS '摘要生成或向量化失败时保存的错误摘要';
COMMENT ON COLUMN knowledge_chat_memory_summaries.created_at IS '创建时间';
COMMENT ON COLUMN knowledge_chat_memory_summaries.updated_at IS '更新时间';

COMMIT;

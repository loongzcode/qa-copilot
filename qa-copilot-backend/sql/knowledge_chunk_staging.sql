-- 超大知识文档分批索引暂存区。
-- Worker 每完成一个 Embedding 批次就提交到这里；全部批次成功后，再由一个
-- 数据库事务替换正式切片，避免任务失败时留下半篇可检索文档。

CREATE TABLE IF NOT EXISTS knowledge_document_chunk_staging (
    id BIGSERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL
        REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    task_id VARCHAR(80) NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    page_no INTEGER,
    section_title VARCHAR(300),
    embedding_model_id INTEGER
        REFERENCES ai_models(id) ON DELETE SET NULL,
    embedding_dimensions INTEGER NOT NULL,
    index_version INTEGER NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(1536) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_knowledge_chunk_staging_task_index
        UNIQUE (document_id, task_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS ix_knowledge_chunk_staging_document_task
    ON knowledge_document_chunk_staging(document_id, task_id);

COMMENT ON TABLE knowledge_document_chunk_staging IS
    '知识文档分批索引暂存区；完整任务成功后原子发布到正式切片表';
COMMENT ON COLUMN knowledge_document_chunk_staging.id IS '暂存切片主键';
COMMENT ON COLUMN knowledge_document_chunk_staging.document_id IS '所属知识文档 ID';
COMMENT ON COLUMN knowledge_document_chunk_staging.task_id IS
    '生成该切片的 Celery 任务 ID，也是阻止旧 Worker 发布结果的栅栏';
COMMENT ON COLUMN knowledge_document_chunk_staging.chunk_index IS '切片在文档内的顺序编号';
COMMENT ON COLUMN knowledge_document_chunk_staging.content IS '切片正文';
COMMENT ON COLUMN knowledge_document_chunk_staging.token_count IS '切片正文 Token 数';
COMMENT ON COLUMN knowledge_document_chunk_staging.page_no IS '来源页码';
COMMENT ON COLUMN knowledge_document_chunk_staging.section_title IS '来源章节标题';
COMMENT ON COLUMN knowledge_document_chunk_staging.embedding_model_id IS '生成向量的 AI 模型 ID';
COMMENT ON COLUMN knowledge_document_chunk_staging.embedding_dimensions IS '向量实际维度';
COMMENT ON COLUMN knowledge_document_chunk_staging.index_version IS '索引规则版本';
COMMENT ON COLUMN knowledge_document_chunk_staging.metadata IS '切片扩展定位信息';
COMMENT ON COLUMN knowledge_document_chunk_staging.embedding IS '尚未发布的 1536 维语义向量';
COMMENT ON COLUMN knowledge_document_chunk_staging.created_at IS '暂存时间';

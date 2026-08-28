-- 为知识切片补充索引兼容性元数据。
-- 相同维度不等于相同向量空间；检索必须同时匹配模型、维度和索引规则版本。

ALTER TABLE knowledge_document_chunks
    ADD COLUMN IF NOT EXISTS embedding_model_id INTEGER,
    ADD COLUMN IF NOT EXISTS embedding_dimensions INTEGER,
    ADD COLUMN IF NOT EXISTS index_version INTEGER;

-- 开发库中的历史切片没有这些字段。模型 ID 根据文档所属知识库回填；当前表的
-- embedding 类型是 vector(1536)，空向量记录也按 1536 记录结构维度。
UPDATE knowledge_document_chunks AS chunk
SET embedding_model_id = knowledge_base.embedding_model_id,
    embedding_dimensions = COALESCE(
        vector_dims(chunk.embedding),
        1536
    ),
    index_version = 1
FROM knowledge_documents AS document
JOIN knowledge_bases AS knowledge_base
  ON knowledge_base.id = document.knowledge_base_id
WHERE document.id = chunk.document_id
  AND (
      chunk.embedding_model_id IS NULL
      OR chunk.embedding_dimensions IS NULL
      OR chunk.index_version IS NULL
  );

ALTER TABLE knowledge_document_chunks
    ALTER COLUMN embedding_dimensions SET DEFAULT 1536,
    ALTER COLUMN embedding_dimensions SET NOT NULL,
    ALTER COLUMN index_version SET DEFAULT 1,
    ALTER COLUMN index_version SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_knowledge_chunks_embedding_model'
    ) THEN
        ALTER TABLE knowledge_document_chunks
            ADD CONSTRAINT fk_knowledge_chunks_embedding_model
            FOREIGN KEY (embedding_model_id)
            REFERENCES ai_models(id)
            ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_knowledge_chunks_embedding_dimensions'
    ) THEN
        ALTER TABLE knowledge_document_chunks
            ADD CONSTRAINT chk_knowledge_chunks_embedding_dimensions
            CHECK (embedding_dimensions > 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_knowledge_chunks_index_version'
    ) THEN
        ALTER TABLE knowledge_document_chunks
            ADD CONSTRAINT chk_knowledge_chunks_index_version
            CHECK (index_version > 0);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS ix_knowledge_document_chunks_compatibility
    ON knowledge_document_chunks(
        embedding_model_id,
        embedding_dimensions,
        index_version
    );

COMMENT ON COLUMN knowledge_document_chunks.embedding_model_id IS
    '生成该切片向量的 AI 模型主键；模型删除后置空，切片不再参与检索';
COMMENT ON COLUMN knowledge_document_chunks.embedding_dimensions IS
    '该切片语义向量的实际维度';
COMMENT ON COLUMN knowledge_document_chunks.index_version IS
    '切片、清洗和向量生成规则版本；版本不匹配时不得参与检索';

-- 中文文本通常没有空格，PostgreSQL 的 simple 全文配置会把连续中文
-- 当成一个完整词元。例如文档“博客文章怎么发布”无法匹配查询“博客文章”。
-- pg_trgm 按连续字符片段建立索引，作为现有 TSVECTOR 检索的中文补充。
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 切片正文是主要检索内容。GIN + gin_trgm_ops 可以加速包含、ILIKE 和
-- trigram 相似度过滤，避免中文查询退化为全表扫描。
CREATE INDEX IF NOT EXISTS ix_knowledge_document_chunks_content_trgm
    ON knowledge_document_chunks
    USING gin (content gin_trgm_ops);

-- 章节标题通常比正文更能概括主题，后续计算词面分数时可以给予更高权重。
CREATE INDEX IF NOT EXISTS ix_knowledge_document_chunks_section_title_trgm
    ON knowledge_document_chunks
    USING gin (section_title gin_trgm_ops);

-- 文档标题也属于重要业务关键词来源，例如“LBlog 系统操作手册”。
CREATE INDEX IF NOT EXISTS ix_knowledge_documents_title_trgm
    ON knowledge_documents
    USING gin (title gin_trgm_ops);

-- 模块名可以帮助“文章管理”“用户管理”这类中文查询命中对应文档。
CREATE INDEX IF NOT EXISTS ix_test_modules_name_trgm
    ON test_modules
    USING gin (name gin_trgm_ops);

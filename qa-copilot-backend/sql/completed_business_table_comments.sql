BEGIN;

-- 项目管理
COMMENT ON TABLE test_projects IS '测试项目，作为测试资产和数据权限的隔离边界';
COMMENT ON COLUMN test_projects.id IS '项目主键';
COMMENT ON COLUMN test_projects.code IS '项目唯一编码';
COMMENT ON COLUMN test_projects.name IS '项目名称';
COMMENT ON COLUMN test_projects.description IS '项目说明';
COMMENT ON COLUMN test_projects.owner_id IS '项目负责人用户 ID';
COMMENT ON COLUMN test_projects.status IS '项目状态：NOT_STARTED 未开始，IN_PROGRESS 进行中，ARCHIVED 已归档';
COMMENT ON COLUMN test_projects.settings IS '项目级测试、知识库和自动化配置';
COMMENT ON COLUMN test_projects.created_at IS '创建时间';
COMMENT ON COLUMN test_projects.updated_at IS '更新时间';
COMMENT ON COLUMN test_projects.deleted_at IS '软删除时间，NULL 表示未删除';

COMMENT ON TABLE test_project_members IS '测试项目成员及其项目内角色';
COMMENT ON COLUMN test_project_members.project_id IS '所属测试项目 ID';
COMMENT ON COLUMN test_project_members.user_id IS '项目成员用户 ID';
COMMENT ON COLUMN test_project_members.member_role IS '项目内角色：OWNER、MANAGER、MEMBER 或 VIEWER';
COMMENT ON COLUMN test_project_members.created_at IS '成员加入项目的时间';

COMMENT ON TABLE test_modules IS '测试项目的树形功能模块';
COMMENT ON COLUMN test_modules.id IS '功能模块主键';
COMMENT ON COLUMN test_modules.project_id IS '所属测试项目 ID';
COMMENT ON COLUMN test_modules.parent_id IS '父模块 ID，NULL 表示根模块';
COMMENT ON COLUMN test_modules.code IS '项目内唯一的模块编码';
COMMENT ON COLUMN test_modules.name IS '模块名称';
COMMENT ON COLUMN test_modules.description IS '模块说明';
COMMENT ON COLUMN test_modules.order_no IS '同级模块的显示顺序';
COMMENT ON COLUMN test_modules.created_at IS '创建时间';
COMMENT ON COLUMN test_modules.updated_at IS '更新时间';

COMMENT ON TABLE test_environments IS '项目测试环境、请求配置和加密变量';
COMMENT ON COLUMN test_environments.id IS '测试环境主键';
COMMENT ON COLUMN test_environments.project_id IS '所属测试项目 ID';
COMMENT ON COLUMN test_environments.name IS '环境名称';
COMMENT ON COLUMN test_environments.base_url IS '环境基础请求地址';
COMMENT ON COLUMN test_environments.headers IS '项目级公共请求头，不保存敏感明文';
COMMENT ON COLUMN test_environments.encrypted_variables IS '使用 DATA_ENCRYPTION_KEY 加密保存的环境变量';
COMMENT ON COLUMN test_environments.enabled IS '是否允许在测试任务中使用该环境';
COMMENT ON COLUMN test_environments.created_by IS '创建用户 ID';
COMMENT ON COLUMN test_environments.created_at IS '创建时间';
COMMENT ON COLUMN test_environments.updated_at IS '更新时间';
COMMENT ON COLUMN test_environments.allowed_hosts IS '允许访问的目标主机或通配规则，用于 SSRF 防护';

-- 知识库与文档
COMMENT ON TABLE knowledge_bases IS '项目知识库及其检索模型配置';
COMMENT ON COLUMN knowledge_bases.id IS '知识库主键';
COMMENT ON COLUMN knowledge_bases.project_id IS '所属测试项目 ID';
COMMENT ON COLUMN knowledge_bases.name IS '知识库名称';
COMMENT ON COLUMN knowledge_bases.description IS '知识库说明';
COMMENT ON COLUMN knowledge_bases.visibility IS '可见范围：PRIVATE、PROJECT 或其他受控范围';
COMMENT ON COLUMN knowledge_bases.embedding_model_id IS '知识切片和查询使用的 Embedding 模型 ID';
COMMENT ON COLUMN knowledge_bases.rerank_model_id IS '候选资料精排使用的 Rerank 模型 ID';
COMMENT ON COLUMN knowledge_bases.enabled IS '知识库是否允许检索和问答';
COMMENT ON COLUMN knowledge_bases.created_by IS '创建用户 ID';
COMMENT ON COLUMN knowledge_bases.created_at IS '创建时间';
COMMENT ON COLUMN knowledge_bases.updated_at IS '更新时间';
COMMENT ON COLUMN knowledge_bases.deleted_at IS '软删除时间，NULL 表示未删除';

COMMENT ON TABLE knowledge_documents IS '知识库文档元数据，文件正文保存在文档存储中';
COMMENT ON COLUMN knowledge_documents.id IS '知识文档主键';
COMMENT ON COLUMN knowledge_documents.knowledge_base_id IS '所属知识库 ID';
COMMENT ON COLUMN knowledge_documents.module_id IS '关联功能模块 ID，NULL 表示未限定模块';
COMMENT ON COLUMN knowledge_documents.document_type IS '文档业务类型，例如操作手册、需求或设计文档';
COMMENT ON COLUMN knowledge_documents.title IS '文档标题';
COMMENT ON COLUMN knowledge_documents.source_type IS '文档来源类型，例如 FILE 或 URL';
COMMENT ON COLUMN knowledge_documents.source_url IS '外部来源地址，本地上传文件通常为空';
COMMENT ON COLUMN knowledge_documents.object_key IS '文档存储中的对象键或相对路径';
COMMENT ON COLUMN knowledge_documents.original_filename IS '用户上传时的原始文件名';
COMMENT ON COLUMN knowledge_documents.mime_type IS '文件 MIME 类型';
COMMENT ON COLUMN knowledge_documents.size_bytes IS '原始文件大小，单位字节';
COMMENT ON COLUMN knowledge_documents.sha256 IS '文件内容 SHA-256，用于完整性校验和重复检测';
COMMENT ON COLUMN knowledge_documents.version IS '文档版本号';
COMMENT ON COLUMN knowledge_documents.parse_status IS '解析索引状态：PENDING、INDEXING、READY 或 FAILED';
COMMENT ON COLUMN knowledge_documents.error_message IS '解析或索引失败时保存的错误摘要';
COMMENT ON COLUMN knowledge_documents.metadata IS '文档扩展元数据';
COMMENT ON COLUMN knowledge_documents.created_by IS '上传或创建文档的用户 ID';
COMMENT ON COLUMN knowledge_documents.created_at IS '创建时间';
COMMENT ON COLUMN knowledge_documents.updated_at IS '更新时间';
COMMENT ON COLUMN knowledge_documents.deleted_at IS '软删除时间，NULL 表示未删除';

COMMENT ON TABLE knowledge_document_chunks IS '知识文档切片、全文检索字段和语义向量';
COMMENT ON COLUMN knowledge_document_chunks.id IS '知识切片主键';
COMMENT ON COLUMN knowledge_document_chunks.document_id IS '所属知识文档 ID';
COMMENT ON COLUMN knowledge_document_chunks.chunk_index IS '切片在文档内的顺序编号';
COMMENT ON COLUMN knowledge_document_chunks.content IS '切片正文';
COMMENT ON COLUMN knowledge_document_chunks.token_count IS '切片正文 Token 数';
COMMENT ON COLUMN knowledge_document_chunks.page_no IS '来源页码，非分页文档可为空';
COMMENT ON COLUMN knowledge_document_chunks.section_title IS '切片所属章节标题';
COMMENT ON COLUMN knowledge_document_chunks.embedding_model_id IS '生成该切片向量的 AI 模型 ID；模型删除后置空';
COMMENT ON COLUMN knowledge_document_chunks.embedding_dimensions IS '该切片语义向量的实际维度';
COMMENT ON COLUMN knowledge_document_chunks.index_version IS '切片、清洗和向量生成规则版本';
COMMENT ON COLUMN knowledge_document_chunks.metadata IS '切片扩展元数据';
COMMENT ON COLUMN knowledge_document_chunks.search_vector IS 'PostgreSQL 全文检索 tsvector';
COMMENT ON COLUMN knowledge_document_chunks.embedding IS '切片正文的 1536 维语义向量';
COMMENT ON COLUMN knowledge_document_chunks.created_at IS '创建时间';

COMMENT ON TABLE knowledge_tags IS '项目级知识标签';
COMMENT ON COLUMN knowledge_tags.id IS '知识标签主键';
COMMENT ON COLUMN knowledge_tags.project_id IS '所属测试项目 ID';
COMMENT ON COLUMN knowledge_tags.name IS '标签名称';
COMMENT ON COLUMN knowledge_tags.color IS '前端展示颜色';
COMMENT ON COLUMN knowledge_tags.created_at IS '创建时间';

COMMENT ON TABLE knowledge_document_tags IS '知识文档与知识标签的多对多关联';
COMMENT ON COLUMN knowledge_document_tags.document_id IS '知识文档 ID';
COMMENT ON COLUMN knowledge_document_tags.tag_id IS '知识标签 ID';

COMMIT;

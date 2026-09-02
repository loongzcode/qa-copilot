BEGIN;

-- 一个测试环境可以连接多个业务数据库；密码使用应用层 DATA_ENCRYPTION_KEY 加密后写入。
CREATE TABLE IF NOT EXISTS environment_data_sources (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES test_projects(id) ON DELETE CASCADE,
    environment_id INTEGER NOT NULL REFERENCES test_environments(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    database_type VARCHAR(20) NOT NULL,
    host VARCHAR(255) NOT NULL,
    port INTEGER NOT NULL,
    database_name VARCHAR(128) NOT NULL,
    schema_name VARCHAR(128),
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    encrypted_credentials TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_environment_data_sources_type
        CHECK (database_type IN ('MYSQL', 'POSTGRESQL')),
    CONSTRAINT uq_environment_data_sources_environment_name
        UNIQUE (environment_id, name)
);

COMMENT ON TABLE environment_data_sources IS '测试环境下供智能数据查询使用的只读数据库连接';
COMMENT ON COLUMN environment_data_sources.config IS 'SSL、字符集、表白名单和敏感字段等非密钥配置';
COMMENT ON COLUMN environment_data_sources.encrypted_credentials IS 'Fernet 加密后的用户名和密码 JSON';
CREATE INDEX IF NOT EXISTS ix_environment_data_sources_project_environment
    ON environment_data_sources(project_id, environment_id, enabled);

-- 元数据快照避免每次提问都扫描 information_schema，也让模型只看到获准的结构。
CREATE TABLE IF NOT EXISTS data_source_metadata_snapshots (
    id SERIAL PRIMARY KEY,
    data_source_id INTEGER NOT NULL REFERENCES environment_data_sources(id) ON DELETE CASCADE,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    table_count INTEGER NOT NULL DEFAULT 0,
    captured_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_data_source_metadata_snapshots_source UNIQUE (data_source_id)
);

COMMENT ON TABLE data_source_metadata_snapshots IS '供智能数据查询使用的表、字段、主外键和注释快照';

-- 查询正文只保存经过行数和字节数限制的结果；完整 SQL 与风险判断用于审计。
CREATE TABLE IF NOT EXISTS data_query_executions (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES test_projects(id) ON DELETE CASCADE,
    environment_id INTEGER NOT NULL REFERENCES test_environments(id) ON DELETE CASCADE,
    data_source_id INTEGER NOT NULL REFERENCES environment_data_sources(id) ON DELETE RESTRICT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    question TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'GENERATING',
    sql_dialect VARCHAR(20) NOT NULL,
    generated_sql TEXT,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    referenced_tables JSONB NOT NULL DEFAULT '[]'::jsonb,
    validation_errors JSONB NOT NULL DEFAULT '[]'::jsonb,
    result_columns JSONB NOT NULL DEFAULT '[]'::jsonb,
    result_rows JSONB NOT NULL DEFAULT '[]'::jsonb,
    result_row_count INTEGER NOT NULL DEFAULT 0,
    truncated BOOLEAN NOT NULL DEFAULT FALSE,
    summary TEXT NOT NULL DEFAULT '',
    visualization JSONB NOT NULL DEFAULT '{}'::jsonb,
    estimated_rows INTEGER,
    full_table_scan BOOLEAN NOT NULL DEFAULT FALSE,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_data_query_executions_status CHECK (
        status IN ('GENERATING', 'VALIDATING', 'EXECUTING', 'SUCCEEDED', 'REJECTED', 'FAILED')
    )
);

COMMENT ON TABLE data_query_executions IS '自然语言问题、受控 SQL、查询结果和风险判断的审计记录';
CREATE INDEX IF NOT EXISTS ix_data_query_executions_project_user
    ON data_query_executions(project_id, user_id, id);
CREATE INDEX IF NOT EXISTS ix_data_query_executions_source_created
    ON data_query_executions(data_source_id, created_at);

COMMIT;

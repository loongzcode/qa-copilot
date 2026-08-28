BEGIN;

CREATE TABLE IF NOT EXISTS knowledge_bases (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES test_projects(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    visibility VARCHAR(20) NOT NULL DEFAULT 'PROJECT',
    embedding_model_id INTEGER NOT NULL REFERENCES ai_models(id) ON DELETE RESTRICT,
    rerank_model_id INTEGER REFERENCES ai_models(id) ON DELETE SET NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_knowledge_bases_project_name UNIQUE (project_id, name),
    CONSTRAINT chk_knowledge_bases_visibility
        CHECK (visibility IN ('PROJECT', 'MANAGERS', 'PRIVATE'))
);

CREATE INDEX IF NOT EXISTS ix_knowledge_bases_project_enabled
    ON knowledge_bases(project_id, enabled);

COMMIT;

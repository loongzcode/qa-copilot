BEGIN;

CREATE TABLE IF NOT EXISTS automation_definition_changes (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES test_projects(id) ON DELETE CASCADE,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    definition_id INTEGER NOT NULL REFERENCES automation_definitions(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    action VARCHAR(20) NOT NULL CHECK (action IN ('CREATED','UPDATED','APPROVED','RETIRED','DELETED')),
    before_snapshot JSONB,
    after_snapshot JSONB,
    changed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_automation_definition_changes_definition
    ON automation_definition_changes(definition_id, id);
CREATE INDEX IF NOT EXISTS ix_automation_definition_changes_project
    ON automation_definition_changes(project_id, id);

COMMENT ON TABLE automation_definition_changes IS '自动化定义不可变变更快照与审计链';
COMMENT ON COLUMN automation_definition_changes.before_snapshot IS '本次操作执行前的定义业务快照；创建操作为空';
COMMENT ON COLUMN automation_definition_changes.after_snapshot IS '本次操作完成后的定义业务快照';
COMMENT ON COLUMN automation_definition_changes.changed_by IS '执行本次变更的用户 ID';

COMMIT;

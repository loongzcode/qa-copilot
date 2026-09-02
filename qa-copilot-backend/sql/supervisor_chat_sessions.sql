-- Supervisor 聊天会话升级：聊天负责连续交互，Run 继续负责可靠执行与审计。
CREATE TABLE IF NOT EXISTS supervisor_sessions (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES test_projects(id) ON DELETE CASCADE,
    title VARCHAR(120) NOT NULL,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE supervisor_sessions IS 'Supervisor 聊天会话；一次会话可包含多次受控运行';
COMMENT ON COLUMN supervisor_sessions.project_id IS '所属项目 ID，也是数据权限边界';
COMMENT ON COLUMN supervisor_sessions.title IS '会话标题，默认取第一条用户目标';
COMMENT ON COLUMN supervisor_sessions.created_by IS '会话创建用户 ID';
COMMENT ON COLUMN supervisor_sessions.deleted_at IS '软删除时间';

CREATE INDEX IF NOT EXISTS ix_supervisor_sessions_project_user_updated
    ON supervisor_sessions(project_id, created_by, updated_at DESC);

ALTER TABLE supervisor_runs
    ADD COLUMN IF NOT EXISTS session_id INTEGER REFERENCES supervisor_sessions(id) ON DELETE CASCADE;

COMMENT ON COLUMN supervisor_runs.session_id IS '所属 Supervisor 聊天会话 ID';
CREATE INDEX IF NOT EXISTS ix_supervisor_runs_session_created
    ON supervisor_runs(session_id, created_at);

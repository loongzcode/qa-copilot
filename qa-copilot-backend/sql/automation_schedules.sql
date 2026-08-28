CREATE TABLE IF NOT EXISTS automation_schedules (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES test_projects(id) ON DELETE CASCADE,
    name VARCHAR(160) NOT NULL,
    definition_id INTEGER NOT NULL REFERENCES automation_definitions(id) ON DELETE RESTRICT,
    environment_id INTEGER NOT NULL REFERENCES test_environments(id) ON DELETE RESTRICT,
    cron_expression VARCHAR(120) NOT NULL,
    timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai',
    timeout_seconds INTEGER NOT NULL DEFAULT 300 CHECK (timeout_seconds BETWEEN 10 AND 7200),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    next_run_at TIMESTAMPTZ NOT NULL,
    last_run_at TIMESTAMPTZ NULL,
    created_by INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_automation_schedules_cron CHECK (length(cron_expression) BETWEEN 5 AND 120)
);
CREATE INDEX IF NOT EXISTS ix_automation_schedules_due ON automation_schedules(enabled, next_run_at, id);
COMMENT ON TABLE automation_schedules IS '接口自动化定时回归计划';
COMMENT ON COLUMN automation_schedules.cron_expression IS '标准五段 Cron 周期表达式';
COMMENT ON COLUMN automation_schedules.next_run_at IS '持久化的下次触发时间，调度器重启后仍可恢复';

INSERT INTO menus (parent_id, route_name, path, component, title, icon, "order", menu_type, permission_code, enabled, hidden, created_at, updated_at)
SELECT id, 'automation_schedules', '/automation/schedules', 'view.automation_schedules', '定时回归', 'mdi:calendar-clock-outline', 2, 'page', NULL, true, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM menus WHERE route_name='automation'
ON CONFLICT (route_name) DO UPDATE SET parent_id=EXCLUDED.parent_id, path=EXCLUDED.path, component=EXCLUDED.component, title=EXCLUDED.title, icon=EXCLUDED.icon, "order"=EXCLUDED."order", permission_code=EXCLUDED.permission_code, enabled=true, hidden=false, updated_at=CURRENT_TIMESTAMP;

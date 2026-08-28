BEGIN;

CREATE TABLE IF NOT EXISTS tool_definitions (
    id SERIAL PRIMARY KEY,
    code VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    risk_level VARCHAR(20) NOT NULL CHECK (risk_level IN ('LOW','MEDIUM','HIGH')),
    required_permission VARCHAR(120) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS external_connections (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES test_projects(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    connection_type VARCHAR(30) NOT NULL CHECK (connection_type IN ('MYSQL','NACOS','BUSINESS_API','DEFECT_PLATFORM')),
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    encrypted_credentials TEXT NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, name)
);
CREATE INDEX IF NOT EXISTS ix_external_connections_project_type ON external_connections(project_id, connection_type);

CREATE TABLE IF NOT EXISTS tool_tasks (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES test_projects(id) ON DELETE CASCADE,
    tool_id INTEGER NOT NULL REFERENCES tool_definitions(id) ON DELETE RESTRICT,
    task_type VARCHAR(40) NOT NULL,
    title VARCHAR(200) NOT NULL,
    risk_level VARCHAR(20) NOT NULL CHECK (risk_level IN ('LOW','MEDIUM','HIGH')),
    status VARCHAR(30) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','PREVIEWED','PENDING_APPROVAL','APPROVED','REJECTED','RUNNING','SUCCEEDED','FAILED','ROLLED_BACK','CANCELLED')),
    requested_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    input_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    preview_data JSONB,
    preview_hash VARCHAR(64),
    result_data JSONB,
    rollback_data JSONB,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_tool_tasks_project_status ON tool_tasks(project_id, status, id);

CREATE TABLE IF NOT EXISTS tool_approvals (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tool_tasks(id) ON DELETE CASCADE,
    requester_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    approver_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    decision VARCHAR(20) NOT NULL CHECK (decision IN ('APPROVED','REJECTED')),
    comment TEXT NOT NULL DEFAULT '',
    preview_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_tool_approvals_task_id ON tool_approvals(task_id);

CREATE TABLE IF NOT EXISTS tool_execution_logs (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tool_tasks(id) ON DELETE CASCADE,
    stage VARCHAR(50) NOT NULL,
    level VARCHAR(20) NOT NULL DEFAULT 'INFO',
    message TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_tool_execution_logs_task_id ON tool_execution_logs(task_id, id);

CREATE TABLE IF NOT EXISTS tool_artifacts (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tool_tasks(id) ON DELETE CASCADE,
    artifact_type VARCHAR(40) NOT NULL,
    name VARCHAR(200) NOT NULL,
    object_key VARCHAR(1000) NOT NULL,
    content_type VARCHAR(160) NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    sha256 VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_tool_artifacts_task ON tool_artifacts(task_id, id);

CREATE TABLE IF NOT EXISTS file_templates (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES test_projects(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    file_format VARCHAR(30) NOT NULL CHECK (file_format IN ('CSV','EXCEL','FIXED_WIDTH_TXT','DELIMITED_TXT','JSON','XML')),
    encoding VARCHAR(20) NOT NULL DEFAULT 'UTF-8',
    delimiter VARCHAR(10),
    fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    header_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    trailer_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, name)
);
CREATE INDEX IF NOT EXISTS ix_file_templates_project ON file_templates(project_id, id);

COMMENT ON TABLE tool_definitions IS '可在受控执行器中使用的工具目录';
COMMENT ON TABLE external_connections IS 'MySQL、Nacos、业务接口和缺陷平台连接';
COMMENT ON TABLE tool_tasks IS '工具任务及完整状态机';
COMMENT ON TABLE tool_approvals IS '高风险工具任务审批审计';
COMMENT ON TABLE tool_execution_logs IS '工具任务阶段与异常审计日志';
COMMENT ON TABLE tool_artifacts IS '工具任务生成的文件、报告和回滚备份';
COMMENT ON TABLE file_templates IS '账务文件字段、格式和校验规则模板';

INSERT INTO tool_definitions (code, name, description, risk_level, required_permission)
VALUES
    ('file.generate', '账务文件生成', '按人工确认字段模板生成账务文件和校验报告', 'LOW', 'tool:execute'),
    ('file.validate', '账务文件校验', '按模板校验上传文件并输出逐行错误报告', 'LOW', 'tool:execute'),
    ('mysql.compare', 'MySQL 结构比较', '只读比较源端与目标端 Schema 并生成差异 SQL', 'LOW', 'tool:execute'),
    ('mysql.sync', 'MySQL 结构同步', '审批后执行允许的 DDL 并记录结果', 'HIGH', 'tool:execute'),
    ('nacos.compare', 'Nacos 配置比较', '读取并脱敏比较源端与目标端配置', 'LOW', 'tool:execute'),
    ('nacos.sync', 'Nacos 配置同步', '备份目标配置后审批发布并支持回滚', 'HIGH', 'tool:execute'),
    ('defect.sync', '缺陷平台同步', '将失败任务或测试缺陷同步到外部平台', 'MEDIUM', 'tool:execute'),
    ('ui.automation', 'UI 自动化', '使用 Playwright 顺序执行受控浏览器动作并生成自愈建议', 'MEDIUM', 'tool:execute')
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    risk_level = EXCLUDED.risk_level,
    required_permission = EXCLUDED.required_permission,
    enabled = true,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO menus (parent_id, route_name, path, component, title, icon, "order", menu_type, permission_code, enabled, hidden, created_at, updated_at)
VALUES (NULL, 'tools', '/tools', 'layout.base', '测试工具', 'mdi:toolbox-outline', 5, 'directory', NULL, true, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (route_name) DO UPDATE SET path=EXCLUDED.path, component=EXCLUDED.component, title=EXCLUDED.title, icon=EXCLUDED.icon, "order"=EXCLUDED."order", enabled=true, hidden=false, updated_at=CURRENT_TIMESTAMP;

WITH page_data(route_name, path, component, title, icon, order_no) AS (
    VALUES
        ('tools_center', '/tools/center', 'view.tools_center', '工具中心', 'mdi:tools', 1),
        ('tools_connections', '/tools/connections', 'view.tools_connections', '外部连接', 'mdi:connection', 2),
        ('tools_file-templates', '/tools/file-templates', 'view.tools_file-templates', '文件模板', 'mdi:file-table-outline', 3),
        ('tools_tasks', '/tools/tasks', 'view.tools_tasks', '任务与审批', 'mdi:clipboard-text-clock-outline', 4)
)
INSERT INTO menus (parent_id, route_name, path, component, title, icon, "order", menu_type, permission_code, enabled, hidden, created_at, updated_at)
SELECT parent.id, page.route_name, page.path, page.component, page.title, page.icon, page.order_no, 'page', NULL, true, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM page_data page CROSS JOIN (SELECT id FROM menus WHERE route_name='tools') parent
ON CONFLICT (route_name) DO UPDATE SET parent_id=EXCLUDED.parent_id, path=EXCLUDED.path, component=EXCLUDED.component, title=EXCLUDED.title, icon=EXCLUDED.icon, "order"=EXCLUDED."order", enabled=true, hidden=false, updated_at=CURRENT_TIMESTAMP;

-- 兼容本功能首次开发时误用下划线路由名的数据，避免菜单表留下两个“文件模板”。
DELETE FROM menus WHERE route_name = 'tools_file_templates';

WITH permission_data(route_name, title, permission_code, order_no) AS (
    VALUES
        ('permission_tool_view', '查看测试工具', 'tool:view', 1),
        ('permission_tool_manage', '管理工具配置', 'tool:manage', 2),
        ('permission_tool_preview', '生成工具预览', 'tool:preview', 3),
        ('permission_tool_execute', '执行工具任务', 'tool:execute', 4),
        ('permission_tool_approve', '审批高风险任务', 'tool:approve', 5),
        ('permission_tool_rollback', '回滚工具任务', 'tool:rollback', 6),
        ('permission_tool_audit', '查看完整工具审计', 'tool:audit', 7)
)
INSERT INTO menus (parent_id, route_name, path, component, title, icon, "order", menu_type, permission_code, enabled, hidden, created_at, updated_at)
SELECT page.id, item.route_name, '', '', item.title, '', item.order_no, 'button', item.permission_code, true, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM permission_data item CROSS JOIN (SELECT id FROM menus WHERE route_name='tools_center') page
ON CONFLICT (route_name) DO UPDATE SET parent_id=EXCLUDED.parent_id, title=EXCLUDED.title, "order"=EXCLUDED."order", permission_code=EXCLUDED.permission_code, enabled=true, hidden=true, updated_at=CURRENT_TIMESTAMP;

INSERT INTO role_menus (role_id, menu_id)
SELECT role.id, menu.id FROM roles role CROSS JOIN menus menu
WHERE role.code='R_SUPER' AND (menu.route_name='tools' OR menu.parent_id=(SELECT id FROM menus WHERE route_name='tools') OR menu.parent_id IN (SELECT id FROM menus WHERE parent_id=(SELECT id FROM menus WHERE route_name='tools')))
ON CONFLICT DO NOTHING;

COMMIT;

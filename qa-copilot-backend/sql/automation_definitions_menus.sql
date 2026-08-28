BEGIN;

INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
VALUES (
    NULL, 'automation', '/automation', 'layout.base', '自动化测试',
    'mdi:robot-industrial-outline', 4, 'directory', NULL, true, false,
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
)
ON CONFLICT (route_name) DO UPDATE SET
    path = EXCLUDED.path,
    component = EXCLUDED.component,
    title = EXCLUDED.title,
    icon = EXCLUDED.icon,
    "order" = EXCLUDED."order",
    enabled = true,
    hidden = false,
    updated_at = CURRENT_TIMESTAMP;

-- 自动化测试占第 4 个一级菜单，原 AI 管理顺延，避免排序相同。
UPDATE menus SET "order" = 5, updated_at = CURRENT_TIMESTAMP
WHERE route_name = 'ai';

INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
SELECT id, 'automation_definitions', '/automation/definitions',
       'view.automation_definitions', '自动化定义', 'mdi:file-code-outline', 1,
       'page', NULL, true, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM menus WHERE route_name = 'automation'
ON CONFLICT (route_name) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    path = EXCLUDED.path,
    component = EXCLUDED.component,
    title = EXCLUDED.title,
    icon = EXCLUDED.icon,
    "order" = EXCLUDED."order",
    enabled = true,
    hidden = false,
    updated_at = CURRENT_TIMESTAMP;

WITH button_data(route_name, title, permission_code, order_no) AS (
    VALUES
        ('permission_automation_view', '查看自动化定义', 'automation:view', 1),
        ('permission_automation_definition_manage', '管理自动化定义', 'automation:definition:manage', 2),
        ('permission_automation_definition_approve', '审批自动化定义', 'automation:definition:approve', 3),
        ('permission_automation_run', '执行和取消自动化任务', 'automation:run', 4)
)
INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
SELECT page.id, button.route_name, '', '', button.title, '', button.order_no,
       'button', button.permission_code, true, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM button_data AS button
CROSS JOIN (SELECT id FROM menus WHERE route_name = 'automation_definitions') AS page
ON CONFLICT (route_name) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    title = EXCLUDED.title,
    "order" = EXCLUDED."order",
    permission_code = EXCLUDED.permission_code,
    enabled = true,
    hidden = true,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO role_menus (role_id, menu_id)
SELECT role.id, menu.id
FROM roles AS role
CROSS JOIN menus AS menu
WHERE role.code = 'R_SUPER'
  AND (
      menu.route_name = 'automation'
      OR menu.parent_id = (SELECT id FROM menus WHERE route_name = 'automation')
      OR menu.parent_id IN (
          SELECT id FROM menus WHERE parent_id = (SELECT id FROM menus WHERE route_name = 'automation')
      )
  )
ON CONFLICT DO NOTHING;

COMMIT;

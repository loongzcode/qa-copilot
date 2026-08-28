BEGIN;

-- Supervisor Agent 页面用于生成受控计划、执行、人工审批和查看审计时间线。
INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
SELECT
    parent.id,
    'requirement_supervisor',
    '/requirement/supervisor',
    'view.requirement_supervisor',
    'Supervisor 编排',
    'mdi:robot-outline',
    5,
    'page',
    NULL,
    true,
    false,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM menus AS parent
WHERE parent.route_name = 'requirement'
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

-- 把已经存在的 Supervisor 按钮权限移动到专属页面下，避免继续挂在需求管理页面。
WITH permission_data(route_name, title, permission_code, order_no) AS (
    VALUES
        ('permission_supervisor_view', '查看 Supervisor 运行', 'supervisor:view', 1),
        ('permission_supervisor_run', '创建和取消 Supervisor 运行', 'supervisor:run', 2),
        ('permission_supervisor_approve', '审批 Supervisor 风险步骤', 'supervisor:approve', 3)
)
INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
SELECT
    page.id, item.route_name, '', '', item.title, '', item.order_no,
    'button', item.permission_code, true, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM permission_data AS item
CROSS JOIN (SELECT id FROM menus WHERE route_name = 'requirement_supervisor') AS page
ON CONFLICT (route_name) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    title = EXCLUDED.title,
    "order" = EXCLUDED."order",
    permission_code = EXCLUDED.permission_code,
    enabled = true,
    hidden = true,
    updated_at = CURRENT_TIMESTAMP;

-- 超级管理员默认拥有页面和三个按钮权限；普通角色可在角色管理中按需分配。
INSERT INTO role_menus (role_id, menu_id)
SELECT role.id, menu.id
FROM roles AS role
CROSS JOIN menus AS menu
WHERE role.code = 'R_SUPER'
  AND menu.route_name IN (
      'requirement_supervisor',
      'permission_supervisor_view',
      'permission_supervisor_run'
      ,'permission_supervisor_approve'
  )
ON CONFLICT DO NOTHING;

COMMIT;

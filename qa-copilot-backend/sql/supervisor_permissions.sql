BEGIN;

WITH permission_data(route_name, title, permission_code, order_no) AS (
    VALUES
        ('permission_supervisor_view', '查看 Supervisor 运行', 'supervisor:view', 20),
        ('permission_supervisor_run', '创建和取消 Supervisor 运行', 'supervisor:run', 21)
)
INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
SELECT
    page.id, item.route_name, '', '', item.title, '', item.order_no,
    'button', item.permission_code, true, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM permission_data AS item
CROSS JOIN (SELECT id FROM menus WHERE route_name = 'requirement_requirements') AS page
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
  AND menu.route_name IN ('permission_supervisor_view', 'permission_supervisor_run')
ON CONFLICT DO NOTHING;

COMMIT;

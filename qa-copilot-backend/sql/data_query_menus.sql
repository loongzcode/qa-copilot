BEGIN;

INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
SELECT
    parent.id, 'project_data-query', '/project/data-query', 'view.project_data-query',
    '数据查询', 'mdi:database-search-outline', 5,
    'page', NULL, TRUE, FALSE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM menus AS parent
WHERE parent.route_name = 'project'
ON CONFLICT (route_name) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    path = EXCLUDED.path,
    component = EXCLUDED.component,
    title = EXCLUDED.title,
    icon = EXCLUDED.icon,
    "order" = EXCLUDED."order",
    enabled = TRUE,
    hidden = FALSE,
    updated_at = CURRENT_TIMESTAMP;

WITH button_data(route_name, title, permission_code, order_no) AS (
    VALUES
        ('permission_data_query_view', '查看数据查询', 'data:query:view', 1),
        ('permission_data_query_source_manage', '管理环境数据源', 'data:query:source:manage', 2),
        ('permission_data_query_execute', '执行智能数据查询', 'data:query:execute', 3)
)
INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
SELECT
    parent.id, item.route_name, '', '', item.title, '', item.order_no,
    'button', item.permission_code, TRUE, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM button_data AS item
CROSS JOIN (SELECT id FROM menus WHERE route_name = 'project_data-query') AS parent
ON CONFLICT (route_name) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    title = EXCLUDED.title,
    "order" = EXCLUDED."order",
    permission_code = EXCLUDED.permission_code,
    enabled = TRUE,
    hidden = TRUE,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO role_menus (role_id, menu_id)
SELECT role.id, menu.id
FROM roles AS role
CROSS JOIN menus AS menu
WHERE role.code = 'R_SUPER'
  AND (
      menu.route_name = 'project_data-query'
      OR menu.parent_id = (SELECT id FROM menus WHERE route_name = 'project_data-query')
  )
ON CONFLICT DO NOTHING;

COMMIT;

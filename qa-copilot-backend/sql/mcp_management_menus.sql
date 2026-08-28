BEGIN;

-- MCP 管理页放在 AI 管理下，用于查看连接信息、工具目录和执行受控只读试调用。
INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
SELECT
    parent.id,
    'ai_mcp',
    '/ai/mcp',
    'view.ai_mcp',
    'MCP 管理',
    'mdi:connection',
    6,
    'page',
    NULL,
    true,
    false,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM menus AS parent
WHERE parent.route_name = 'ai'
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

WITH permission_data(route_name, title, permission_code, order_no) AS (
    VALUES
        ('permission_mcp_view', '查看 MCP 配置与工具', 'mcp:view', 1),
        ('permission_mcp_invoke', '试调用 MCP 只读工具', 'mcp:invoke', 2)
)
INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
SELECT
    page.id, item.route_name, '', '', item.title, '', item.order_no,
    'button', item.permission_code, true, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM permission_data AS item
CROSS JOIN (SELECT id FROM menus WHERE route_name = 'ai_mcp') AS page
ON CONFLICT (route_name) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    title = EXCLUDED.title,
    "order" = EXCLUDED."order",
    permission_code = EXCLUDED.permission_code,
    enabled = true,
    hidden = true,
    updated_at = CURRENT_TIMESTAMP;

-- 超级管理员默认拥有页面与试调用权限；普通角色由角色管理页面按需授权。
INSERT INTO role_menus (role_id, menu_id)
SELECT role.id, menu.id
FROM roles AS role
CROSS JOIN menus AS menu
WHERE role.code = 'R_SUPER'
  AND menu.route_name IN ('ai_mcp', 'permission_mcp_view', 'permission_mcp_invoke')
ON CONFLICT DO NOTHING;

COMMIT;

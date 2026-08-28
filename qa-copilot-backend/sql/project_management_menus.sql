BEGIN;

-- 可重复执行：为现有数据库补充项目管理目录和四个页面。
INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
VALUES (
    NULL, 'project', '/project', 'layout.base', '项目管理',
    'mdi:folder-cog-outline', 1, 'directory', NULL, true, false,
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

WITH page_data(route_name, path, component, title, icon, order_no) AS (
    VALUES
        ('project_info', '/project/info', 'view.project_info', '项目信息', 'mdi:folder-information-outline', 1),
        ('project_members', '/project/members', 'view.project_members', '项目成员', 'mdi:account-group-outline', 2),
        ('project_modules', '/project/modules', 'view.project_modules', '功能模块', 'mdi:file-tree-outline', 3),
        ('project_environments', '/project/environments', 'view.project_environments', '测试环境', 'mdi:server-network-outline', 4)
)
INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
SELECT
    parent.id, page.route_name, page.path, page.component, page.title, page.icon, page.order_no,
    'page', NULL, true, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM page_data AS page
CROSS JOIN (SELECT id FROM menus WHERE route_name = 'project') AS parent
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

WITH button_data(parent_route, route_name, title, permission_code, order_no) AS (
    VALUES
        ('project_info', 'permission_project_info_view', '查看项目', 'project:info:view', 1),
        ('project_info', 'permission_project_info_create', '创建项目', 'project:info:create', 2),
        ('project_info', 'permission_project_info_update', '编辑项目', 'project:info:update', 3),
        ('project_info', 'permission_project_info_archive', '归档项目', 'project:info:archive', 4),
        ('project_members', 'permission_project_member_view', '查看成员', 'project:member:view', 1),
        ('project_members', 'permission_project_member_manage', '管理成员', 'project:member:manage', 2),
        ('project_modules', 'permission_project_module_view', '查看模块', 'project:module:view', 1),
        ('project_modules', 'permission_project_module_manage', '管理模块', 'project:module:manage', 2),
        ('project_environments', 'permission_project_environment_view', '查看环境', 'project:environment:view', 1),
        ('project_environments', 'permission_project_environment_manage', '管理环境', 'project:environment:manage', 2),
        ('project_environments', 'permission_project_environment_test', '测试连接', 'project:environment:test', 3)
)
INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
SELECT
    parent.id, button.route_name, '', '', button.title, '', button.order_no,
    'button', button.permission_code, true, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM button_data AS button
JOIN menus AS parent ON parent.route_name = button.parent_route
ON CONFLICT (route_name) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    title = EXCLUDED.title,
    "order" = EXCLUDED."order",
    permission_code = EXCLUDED.permission_code,
    enabled = true,
    hidden = true,
    updated_at = CURRENT_TIMESTAMP;

-- 超级管理员自动获得新菜单；其他角色可在“角色管理”中按需授权。
INSERT INTO role_menus (role_id, menu_id)
SELECT role.id, menu.id
FROM roles AS role
CROSS JOIN menus AS menu
WHERE role.code = 'R_SUPER'
  AND (
      menu.route_name = 'project'
      OR menu.parent_id = (SELECT id FROM menus WHERE route_name = 'project')
      OR menu.parent_id IN (
          SELECT id FROM menus WHERE parent_id = (SELECT id FROM menus WHERE route_name = 'project')
      )
  )
ON CONFLICT DO NOTHING;

COMMIT;

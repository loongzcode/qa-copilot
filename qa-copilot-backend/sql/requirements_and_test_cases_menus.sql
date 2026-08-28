BEGIN;

-- 可重复执行：新增“需求与用例”目录。
INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
VALUES (
    NULL, 'requirement', '/requirement', 'layout.base', '需求与用例',
    'mdi:clipboard-text-search-outline', 3, 'directory', NULL, true, false,
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

-- 新目录位于知识库之后，AI 管理顺延一位。
UPDATE menus SET "order" = 4, updated_at = CURRENT_TIMESTAMP
WHERE route_name = 'ai';

WITH page_data(route_name, path, component, title, icon, order_no, hidden) AS (
    VALUES
        ('requirement_requirements', '/requirement/requirements', 'view.requirement_requirements', '需求管理', 'mdi:file-document-edit-outline', 1, false),
        ('requirement_coverage', '/requirement/coverage', 'view.requirement_coverage', '覆盖分析', 'mdi:table-search', 2, false),
        ('requirement_test-cases', '/requirement/test-cases', 'view.requirement_test-cases', '测试用例', 'mdi:clipboard-list-outline', 3, false),
        ('requirement_review', '/requirement/review', 'view.requirement_review', '生成审核', 'mdi:clipboard-check-multiple-outline', 4, false),
        ('requirement_detail', '/requirement/detail', 'view.requirement_detail', '需求详情', 'mdi:file-document-outline', 5, true)
)
INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
SELECT
    parent.id, page.route_name, page.path, page.component, page.title, page.icon, page.order_no,
    'page', NULL, true, page.hidden, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM page_data AS page
CROSS JOIN (SELECT id FROM menus WHERE route_name = 'requirement') AS parent
ON CONFLICT (route_name) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    path = EXCLUDED.path,
    component = EXCLUDED.component,
    title = EXCLUDED.title,
    icon = EXCLUDED.icon,
    "order" = EXCLUDED."order",
    enabled = true,
    hidden = EXCLUDED.hidden,
    updated_at = CURRENT_TIMESTAMP;

WITH button_data(parent_route, route_name, title, permission_code, order_no) AS (
    VALUES
        ('requirement_requirements', 'permission_requirement_view', '查看需求', 'requirement:view', 1),
        ('requirement_requirements', 'permission_requirement_manage', '管理需求与需求点', 'requirement:manage', 2),
        ('requirement_requirements', 'permission_requirement_extract', '执行需求拆解', 'requirement:extract', 3),
        ('requirement_coverage', 'permission_test_case_generate', '覆盖分析与生成', 'test:case:generate', 1),
        ('requirement_test-cases', 'permission_test_case_view', '查看测试用例', 'test:case:view', 1),
        ('requirement_test-cases', 'permission_test_case_manage', '管理测试用例', 'test:case:manage', 2),
        ('requirement_review', 'permission_test_case_review', '审核和发布用例', 'test:case:review', 1)
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

-- 需求详情是隐藏页面，也必须分配给超级管理员，否则动态路由无法进入。
INSERT INTO role_menus (role_id, menu_id)
SELECT role.id, menu.id
FROM roles AS role
CROSS JOIN menus AS menu
WHERE role.code = 'R_SUPER'
  AND (
      menu.route_name = 'requirement'
      OR menu.parent_id = (SELECT id FROM menus WHERE route_name = 'requirement')
      OR menu.parent_id IN (
          SELECT id FROM menus WHERE parent_id = (SELECT id FROM menus WHERE route_name = 'requirement')
      )
  )
ON CONFLICT DO NOTHING;

COMMIT;

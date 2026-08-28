BEGIN;

-- 可重复执行：新增“测试知识库”目录及三个业务页面。
INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
VALUES (
    NULL, 'knowledge', '/knowledge', 'layout.base', '测试知识库',
    'mdi:bookshelf', 2, 'directory', NULL, true, false,
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

-- 知识库排在项目管理之后，AI 管理顺延。
UPDATE menus SET "order" = 3, updated_at = CURRENT_TIMESTAMP
WHERE route_name = 'ai';

WITH page_data(route_name, path, component, title, icon, order_no) AS (
    VALUES
        ('knowledge_bases', '/knowledge/bases', 'view.knowledge_bases', '知识库管理', 'mdi:database-outline', 1),
        ('knowledge_documents', '/knowledge/documents', 'view.knowledge_documents', '文档管理', 'mdi:file-document-multiple-outline', 2),
        ('knowledge_chat', '/knowledge/chat', 'view.knowledge_chat', '知识问答', 'mdi:message-text-outline', 3)
)
INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
SELECT
    parent.id, page.route_name, page.path, page.component, page.title, page.icon, page.order_no,
    'page', NULL, true, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM page_data AS page
CROSS JOIN (SELECT id FROM menus WHERE route_name = 'knowledge') AS parent
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
        ('knowledge_bases', 'permission_knowledge_base_view', '查看知识库', 'knowledge:base:view', 1),
        ('knowledge_bases', 'permission_knowledge_base_manage', '管理知识库', 'knowledge:base:manage', 2),
        ('knowledge_documents', 'permission_knowledge_document_view', '查看文档', 'knowledge:document:view', 1),
        ('knowledge_documents', 'permission_knowledge_document_upload', '上传文档', 'knowledge:document:upload', 2),
        ('knowledge_documents', 'permission_knowledge_document_manage', '管理文档', 'knowledge:document:manage', 3),
        ('knowledge_documents', 'permission_knowledge_document_index', '执行索引', 'knowledge:document:index', 4),
        ('knowledge_chat', 'permission_knowledge_chat_use', '使用知识问答', 'knowledge:chat:use', 1)
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

-- 超级管理员自动获得新菜单；其他角色在角色管理中按需授权。
INSERT INTO role_menus (role_id, menu_id)
SELECT role.id, menu.id
FROM roles AS role
CROSS JOIN menus AS menu
WHERE role.code = 'R_SUPER'
  AND (
      menu.route_name = 'knowledge'
      OR menu.parent_id = (SELECT id FROM menus WHERE route_name = 'knowledge')
      OR menu.parent_id IN (
          SELECT id FROM menus WHERE parent_id = (SELECT id FROM menus WHERE route_name = 'knowledge')
      )
  )
ON CONFLICT DO NOTHING;

COMMIT;

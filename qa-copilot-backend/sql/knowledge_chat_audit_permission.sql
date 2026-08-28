INSERT INTO menus (parent_id, route_name, path, component, title, icon, "order", menu_type, permission_code, enabled, hidden, created_at, updated_at)
SELECT id, 'knowledge_chat_audit', '', '', '审计知识问答会话', '', 90, 'button', 'knowledge:chat:audit', true, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM menus WHERE route_name='knowledge_chat'
ON CONFLICT (route_name) DO UPDATE SET parent_id=EXCLUDED.parent_id, title=EXCLUDED.title, "order"=EXCLUDED."order", permission_code=EXCLUDED.permission_code, enabled=true, hidden=true, updated_at=CURRENT_TIMESTAMP;

INSERT INTO role_menus(role_id, menu_id)
SELECT role.id, menu.id FROM roles role CROSS JOIN menus menu
WHERE role.code='R_SUPER' AND menu.route_name='knowledge_chat_audit'
ON CONFLICT DO NOTHING;

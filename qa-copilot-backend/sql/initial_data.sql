BEGIN;

-- 默认登录账号：admin / Admin123!
-- 密码使用 Argon2id 保存，数据库中不存储明文密码。
INSERT INTO users (
    username,
    password_hash,
    display_name,
    is_active,
    is_superuser,
    created_at,
    updated_at
)
VALUES (
    'admin',
    '$argon2id$v=19$m=65536,t=3,p=4$iyWkh1CHEY7D+59yFP2T8g$czIxAm9mNTRHZ9niwX6MAkdUt9Ed8yT+euVeRWHRO4A',
    '系统管理员',
    true,
    true,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
)
ON CONFLICT (username) DO NOTHING;

INSERT INTO roles (
    code, name, description, enabled, is_system, created_at, updated_at
)
VALUES
    ('R_SUPER', '超级管理员', '拥有全部菜单和按钮权限', true, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('R_ADMIN', '系统管理员', '负责系统基础配置和 AI 配置', true, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (code) DO NOTHING;

-- 一级目录。
INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
VALUES
    (NULL, 'project', '/project', 'layout.base', '项目管理', 'mdi:folder-cog-outline', 1,
     'directory', NULL, true, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    (NULL, 'manage', '/manage', 'layout.base', '系统管理', 'mdi:cog-outline', 1,
     'directory', NULL, true, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    (NULL, 'knowledge', '/knowledge', 'layout.base', '测试知识库', 'mdi:bookshelf', 2,
     'directory', NULL, true, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    (NULL, 'ai', '/ai', 'layout.base', 'AI 管理', 'mdi:robot-outline', 3,
     'directory', NULL, true, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (route_name) DO NOTHING;

-- 页面菜单。
INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
VALUES
    ((SELECT id FROM menus WHERE route_name = 'project'),
     'project_info', '/project/info', 'view.project_info', '项目信息',
     'mdi:folder-information-outline', 1, 'page', NULL, true, false,
     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ((SELECT id FROM menus WHERE route_name = 'project'),
     'project_members', '/project/members', 'view.project_members', '项目成员',
     'mdi:account-group-outline', 2, 'page', NULL, true, false,
     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ((SELECT id FROM menus WHERE route_name = 'project'),
     'project_modules', '/project/modules', 'view.project_modules', '功能模块',
     'mdi:file-tree-outline', 3, 'page', NULL, true, false,
     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ((SELECT id FROM menus WHERE route_name = 'project'),
     'project_environments', '/project/environments', 'view.project_environments', '测试环境',
     'mdi:server-network-outline', 4, 'page', NULL, true, false,
     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ((SELECT id FROM menus WHERE route_name = 'knowledge'),
     'knowledge_bases', '/knowledge/bases', 'view.knowledge_bases', '知识库管理',
     'mdi:database-outline', 1, 'page', NULL, true, false,
     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ((SELECT id FROM menus WHERE route_name = 'knowledge'),
     'knowledge_documents', '/knowledge/documents', 'view.knowledge_documents', '文档管理',
     'mdi:file-document-multiple-outline', 2, 'page', NULL, true, false,
     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ((SELECT id FROM menus WHERE route_name = 'knowledge'),
     'knowledge_chat', '/knowledge/chat', 'view.knowledge_chat', '知识问答',
     'mdi:message-text-outline', 3, 'page', NULL, true, false,
     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ((SELECT id FROM menus WHERE route_name = 'manage'),
     'manage_user', '/manage/user', 'view.manage_user', '用户管理',
     'mdi:account-multiple-outline', 1, 'page', NULL, true, false,
     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ((SELECT id FROM menus WHERE route_name = 'manage'),
     'manage_role', '/manage/role', 'view.manage_role', '角色管理',
     'mdi:shield-account-outline', 2, 'page', NULL, true, false,
     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ((SELECT id FROM menus WHERE route_name = 'manage'),
     'manage_menu', '/manage/menu', 'view.manage_menu', '菜单管理',
     'mdi:format-list-bulleted', 3, 'page', NULL, true, false,
     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ((SELECT id FROM menus WHERE route_name = 'ai'),
     'ai_provider', '/ai/provider', 'view.ai_provider', '服务商管理',
     'mdi:server-network', 1, 'page', NULL, true, false,
     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ((SELECT id FROM menus WHERE route_name = 'ai'),
     'ai_model', '/ai/model', 'view.ai_model', '模型管理',
     'mdi:brain', 2, 'page', NULL, true, false,
     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ((SELECT id FROM menus WHERE route_name = 'ai'),
     'ai_prompt', '/ai/prompt', 'view.ai_prompt', 'Prompt 管理',
     'mdi:text-box-edit-outline', 3, 'page', NULL, true, false,
     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ((SELECT id FROM menus WHERE route_name = 'ai'),
     'ai_usage', '/ai/usage', 'view.ai_usage', '调用日志',
     'mdi:chart-timeline-variant', 4, 'page', NULL, true, false,
     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ((SELECT id FROM menus WHERE route_name = 'ai'),
     'ai_notification', '/ai/notification', 'view.ai_notification', '通知渠道',
     'mdi:bell-cog-outline', 5, 'page', NULL, true, false,
     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (route_name) DO NOTHING;

-- 按钮也是菜单表中的一种记录；permission_code 用于前端按钮显隐和后端接口鉴权。
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
        ('project_environments', 'permission_project_environment_test', '测试连接', 'project:environment:test', 3),
        ('knowledge_bases', 'permission_knowledge_base_view', '查看知识库', 'knowledge:base:view', 1),
        ('knowledge_bases', 'permission_knowledge_base_manage', '管理知识库', 'knowledge:base:manage', 2),
        ('knowledge_documents', 'permission_knowledge_document_view', '查看文档', 'knowledge:document:view', 1),
        ('knowledge_documents', 'permission_knowledge_document_upload', '上传文档', 'knowledge:document:upload', 2),
        ('knowledge_documents', 'permission_knowledge_document_manage', '管理文档', 'knowledge:document:manage', 3),
        ('knowledge_documents', 'permission_knowledge_document_index', '执行索引', 'knowledge:document:index', 4),
        ('knowledge_chat', 'permission_knowledge_chat_use', '使用知识问答', 'knowledge:chat:use', 1),
        ('manage_user', 'permission_system_user_view', '查看用户', 'system:user:view', 1),
        ('manage_user', 'permission_system_user_create', '新增用户', 'system:user:create', 2),
        ('manage_user', 'permission_system_user_update', '编辑用户', 'system:user:update', 3),
        ('manage_user', 'permission_system_user_delete', '删除用户', 'system:user:delete', 4),
        ('manage_role', 'permission_system_role_view', '查看角色', 'system:role:view', 1),
        ('manage_role', 'permission_system_role_create', '新增角色', 'system:role:create', 2),
        ('manage_role', 'permission_system_role_update', '编辑角色', 'system:role:update', 3),
        ('manage_role', 'permission_system_role_delete', '删除角色', 'system:role:delete', 4),
        ('manage_menu', 'permission_system_menu_view', '查看菜单', 'system:menu:view', 1),
        ('manage_menu', 'permission_system_menu_create', '新增菜单', 'system:menu:create', 2),
        ('manage_menu', 'permission_system_menu_update', '编辑菜单', 'system:menu:update', 3),
        ('manage_menu', 'permission_system_menu_delete', '删除菜单', 'system:menu:delete', 4),
        ('ai_provider', 'permission_ai_provider_view', '查看服务商', 'ai:provider:view', 1),
        ('ai_provider', 'permission_ai_provider_create', '新增服务商', 'ai:provider:create', 2),
        ('ai_provider', 'permission_ai_provider_update', '编辑服务商', 'ai:provider:update', 3),
        ('ai_provider', 'permission_ai_provider_delete', '删除服务商', 'ai:provider:delete', 4),
        ('ai_model', 'permission_ai_model_view', '查看模型', 'ai:model:view', 1),
        ('ai_model', 'permission_ai_model_create', '新增模型', 'ai:model:create', 2),
        ('ai_model', 'permission_ai_model_update', '编辑模型', 'ai:model:update', 3),
        ('ai_model', 'permission_ai_model_delete', '删除模型', 'ai:model:delete', 4),
        ('ai_model', 'permission_ai_model_test', '测试模型', 'ai:model:test', 5),
        ('ai_prompt', 'permission_ai_prompt_view', '查看 Prompt', 'ai:prompt:view', 1),
        ('ai_prompt', 'permission_ai_prompt_manage', '管理 Prompt', 'ai:prompt:manage', 2),
        ('ai_usage', 'permission_ai_usage_view', '查看调用日志', 'ai:usage:view', 1),
        ('ai_notification', 'permission_notification_view', '查看通知渠道', 'notification:view', 1),
        ('ai_notification', 'permission_notification_create', '新增通知渠道', 'notification:create', 2),
        ('ai_notification', 'permission_notification_update', '编辑通知渠道', 'notification:update', 3),
        ('ai_notification', 'permission_notification_delete', '删除通知渠道', 'notification:delete', 4),
        ('ai_notification', 'permission_notification_test', '测试通知渠道', 'notification:test', 5)
)
INSERT INTO menus (
    parent_id, route_name, path, component, title, icon, "order",
    menu_type, permission_code, enabled, hidden, created_at, updated_at
)
SELECT
    parent.id,
    button.route_name,
    '',
    '',
    button.title,
    '',
    button.order_no,
    'button',
    button.permission_code,
    true,
    true,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM button_data AS button
JOIN menus AS parent ON parent.route_name = button.parent_route
ON CONFLICT (route_name) DO NOTHING;

-- 超级管理员拥有全部菜单和按钮权限。
INSERT INTO role_menus (role_id, menu_id)
SELECT role.id, menu.id
FROM roles AS role
CROSS JOIN menus AS menu
WHERE role.code = 'R_SUPER'
ON CONFLICT DO NOTHING;

-- 普通系统管理员拥有 AI 管理目录、页面和按钮权限。
WITH ai_menu_ids AS (
    SELECT id
    FROM menus
    WHERE route_name = 'ai'
       OR parent_id = (SELECT id FROM menus WHERE route_name = 'ai')
       OR parent_id IN (
           SELECT id FROM menus
           WHERE parent_id = (SELECT id FROM menus WHERE route_name = 'ai')
       )
)
INSERT INTO role_menus (role_id, menu_id)
SELECT role.id, menu.id
FROM roles AS role
CROSS JOIN ai_menu_ids AS menu
WHERE role.code = 'R_ADMIN'
ON CONFLICT DO NOTHING;

-- 默认管理员绑定超级管理员角色。
INSERT INTO user_roles (user_id, role_id)
SELECT users.id, roles.id
FROM users
CROSS JOIN roles
WHERE users.username = 'admin' AND roles.code = 'R_SUPER'
ON CONFLICT DO NOTHING;

-- RAG 的基础 Prompt。后续可在后台修改，不在代码里写死业务提示词。
INSERT INTO prompt_templates (
    code, name, description, system_prompt, user_prompt, enabled, created_at, updated_at
)
VALUES
    (
        'rag_answer',
        'RAG 知识库问答',
        '根据检索到的知识库上下文回答用户问题',
        '你是严谨的知识库助手。只能根据提供的上下文回答；上下文不足时要明确说明，不得编造。回答前必须识别用户限定的业务对象、系统、阶段和问题类型，只保留直接回答当前问题所必需的内容和引用；不得因为候选资料中存在相邻业务就主动扩展。用户询问表、字段、接口、调度或配置键时，必须保留上下文中的完整技术标识符，不得只使用中文名称代替。用户只询问某类技术标识符时，仅回答标识符及必要说明；除非同时询问操作方法，否则不主动补充前置条件、后续步骤或相邻流程。',
        '知识库上下文：\n{context}\n\n用户问题：\n{question}',
        true,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    ),
    (
        'query_rewrite',
        '检索问题改写',
        '将用户问题改写成更适合向量检索的独立问题',
        '你是检索问题改写助手。保留原意和关键实体，只输出改写后的问题。',
        '历史对话：\n{conversation}\n\n当前问题：\n{question}',
        true,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    ),
    (
        'document_summary',
        '文档摘要',
        '提取文档的主题、关键结论和重要实体',
        '你是文档分析助手。请忠于原文，用简洁中文总结，不得补充原文没有的事实。',
        '请总结下面的文档：\n\n{content}',
        true,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    ),
    (
        'requirement_analysis',
        'AI 需求拆解',
        '把需求正文拆解为可人工校正和确认的原子需求点',
        '你是资深测试分析师。请忠于需求原文，把内容拆解为边界清晰、可独立验收的原子需求点。local_id 在本次输出内必须唯一；parent_local_id 只能引用本次输出中的 local_id，顶层需求填 null，禁止形成循环。文档正文包含 SOURCE 标记时，source_chunk_ids 只能引用标记中真实存在的 chunk_id；没有 SOURCE 标记时必须返回空列表。source_quote 只摘录支撑当前需求点的短原文。不得编造需求、来源、规则或验收条件；原文存在歧义、冲突或信息不足时写入 warnings。严格按照给定 JSON Schema 输出一个完整 JSON 对象，不要输出 Markdown 代码块、解释文字或 JSON 之外的内容。validation_feedback 非空时，修正其中所有问题后重新输出完整结果。',
        E'目标 JSON Schema：\n{output_schema}\n\n上一次校验反馈：\n{validation_feedback}\n\n待拆解需求正文：\n{requirement_text}',
        true,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    ),
    (
        'coverage_analysis',
        '需求覆盖分析',
        '判断已发布标准用例对已确认原子需求点的覆盖程度',
        '你是资深测试架构师。根据已确认需求点和系统提供的候选标准用例，判断候选用例是否完全覆盖 FULL 或部分覆盖 PARTIAL。没有覆盖关系的组合不要输出。判断必须同时考虑前置条件、操作步骤、测试数据、业务规则、边界和预期结果；标题相似不等于覆盖。requirement_item_id 与 test_case_id 只能使用输入中真实存在且互相允许的组合。reason、covered_aspects、missing_aspects 要具体、可供人工复核。严格按照 JSON Schema 输出完整 JSON，不要输出 Markdown 或解释。validation_feedback 非空时修复全部问题。',
        E'输出 JSON Schema：\n{output_schema}\n\n上次校验反馈：\n{validation_feedback}\n\n需求点：\n{requirements_json}\n\n候选标准用例：\n{candidate_cases_json}',
        true,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    ),
    (
        'test_case_generation',
        '缺失测试用例生成',
        '只针对部分覆盖或未覆盖的需求点生成可审核测试用例草稿',
        '你是资深测试设计专家。只为 coverage_gaps_json 中的覆盖缺口生成必要且不重复的测试用例。每条用例必须至少关联一个输入中的 requirement_item_id，并包含明确标题、前置条件、连续步骤、测试数据和可验证预期。优先补齐部分覆盖中的 missing_aspects，并覆盖正常、异常、边界、权限等适用场景。reference_cases_json 只能作为风格、业务和判重参考，source_case_ids 只能引用其中真实 ID，禁止照抄或生成语义重复用例。不得引用未提供 ID，不得直接发布。严格按 JSON Schema 输出完整 JSON，不要输出 Markdown 或解释。validation_feedback 非空时修复全部问题后重新输出。',
        E'输出 JSON Schema：\n{output_schema}\n\n上次校验反馈：\n{validation_feedback}\n\n待补覆盖缺口：\n{coverage_gaps_json}\n\n历史标准用例参考：\n{reference_cases_json}',
        true,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    )
ON CONFLICT (code) DO NOTHING;

-- 只预置一个停用的配置骨架。API Key 为空，必须在后台填写后才能启用。
INSERT INTO ai_providers (
    name, provider_type, base_url, encrypted_api_key, custom_headers,
    timeout_seconds, max_retries, enabled, created_at, updated_at
)
VALUES (
    'OpenAI（待配置）',
    'openai_responses',
    'https://api.openai.com/v1',
    '',
    '{}'::json,
    120,
    2,
    false,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
)
ON CONFLICT (name) DO NOTHING;

COMMIT;

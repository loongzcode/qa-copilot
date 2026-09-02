class Permission:
    """集中保存权限码；每个常量表示一项可以分配给角色的操作权限。"""

    # 查看首页仪表盘及其统计信息。
    DASHBOARD_VIEW = "dashboard:view"

    # 查看情报来源列表和详情。
    SOURCE_VIEW = "source:view"
    # 新增情报来源。
    SOURCE_CREATE = "source:create"
    # 编辑情报来源配置。
    SOURCE_UPDATE = "source:update"
    # 删除情报来源。
    SOURCE_DELETE = "source:delete"
    # 主动触发情报来源的数据抓取。
    SOURCE_FETCH = "source:fetch"

    # 查看已抓取的情报条目。
    ITEM_VIEW = "item:view"
    # 编辑情报条目的业务信息。
    ITEM_UPDATE = "item:update"
    # 调用 AI 对情报条目进行分析。
    ITEM_ANALYZE = "item:analyze"

    # 查看文章列表和详情。
    ARTICLE_VIEW = "article:view"
    # 创建文章。
    ARTICLE_CREATE = "article:create"
    # 编辑文章。
    ARTICLE_UPDATE = "article:update"
    # 删除文章。
    ARTICLE_DELETE = "article:delete"
    # 使用 AI 根据已有内容生成文章。
    ARTICLE_GENERATE = "article:generate"

    # 查看 AI 管理模块的基础信息。
    AI_VIEW = "ai:view"
    # 新增 AI 服务商配置。
    AI_PROVIDER_CREATE = "ai:provider:create"
    # 编辑 AI 服务商配置及密钥。
    AI_PROVIDER_UPDATE = "ai:provider:update"
    # 删除 AI 服务商配置。
    AI_PROVIDER_DELETE = "ai:provider:delete"
    # 新增服务商下的模型配置。
    AI_MODEL_CREATE = "ai:model:create"
    # 编辑模型参数、用途和启用状态。
    AI_MODEL_UPDATE = "ai:model:update"
    # 删除模型配置。
    AI_MODEL_DELETE = "ai:model:delete"
    # 发起一次模型连通性或能力测试。
    AI_MODEL_TEST = "ai:model:test"
    # 创建、编辑、启停和删除 Prompt 模板。
    AI_PROMPT_MANAGE = "ai:prompt:manage"
    # 查看 Prompt 模板列表、详情和内容。
    AI_PROMPT_VIEW = "ai:prompt:view"
    # 查看 AI 调用日志、Token 用量、耗时统计和脱敏后的失败原因。
    AI_USAGE_VIEW = "ai:usage:view"

    # 查看自动化任务、运行状态和结果。
    AUTOMATION_VIEW = "automation:view"
    # 创建、编辑和删除尚未审批的受控自动化测试定义。
    AUTOMATION_DEFINITION_MANAGE = "automation:definition:manage"
    # 审批自动化测试定义，或将已审批版本退出使用。
    AUTOMATION_DEFINITION_APPROVE = "automation:definition:approve"
    # 创建并启动自动化测试任务。
    AUTOMATION_RUN = "automation:run"

    # 查看有数据权限的项目列表和项目详情。
    PROJECT_INFO_VIEW = "project:info:view"
    # 创建测试项目。
    PROJECT_INFO_CREATE = "project:info:create"
    # 编辑项目信息或将草稿项目启动。
    PROJECT_INFO_UPDATE = "project:info:update"
    # 将进行中的项目归档。
    PROJECT_INFO_ARCHIVE = "project:info:archive"

    # 查看项目成员及成员角色。
    PROJECT_MEMBER_VIEW = "project:member:view"
    # 添加、移除项目成员以及修改成员角色。
    PROJECT_MEMBER_MANAGE = "project:member:manage"

    # 查看项目功能模块树。
    PROJECT_MODULE_VIEW = "project:module:view"
    # 创建、编辑、移动和删除功能模块。
    PROJECT_MODULE_MANAGE = "project:module:manage"

    # 查看项目测试环境及脱敏后的变量。
    PROJECT_ENVIRONMENT_VIEW = "project:environment:view"
    # 创建、编辑、启停和删除测试环境。
    PROJECT_ENVIRONMENT_MANAGE = "project:environment:manage"
    # 使用测试环境配置发起连接测试。
    PROJECT_ENVIRONMENT_TEST = "project:environment:test"

    # 查看环境数据源、元数据和本人可访问项目的数据查询历史。
    DATA_QUERY_VIEW = "data:query:view"
    # 创建、编辑、测试和删除测试环境的数据源连接。
    DATA_QUERY_SOURCE_MANAGE = "data:query:source:manage"
    # 使用自然语言生成并执行受控只读 SQL。
    DATA_QUERY_EXECUTE = "data:query:execute"

    # 查看符合 PROJECT、MANAGERS、PRIVATE 数据权限的知识库。
    KNOWLEDGE_BASE_VIEW = "knowledge:base:view"
    # 创建、编辑、启停和删除知识库。
    KNOWLEDGE_BASE_MANAGE = "knowledge:base:manage"

    # 查看知识文档、版本以及解析和索引状态。
    KNOWLEDGE_DOCUMENT_VIEW = "knowledge:document:view"
    # 上传 PDF、DOCX、Markdown、TXT 等原始知识文档。
    KNOWLEDGE_DOCUMENT_UPLOAD = "knowledge:document:upload"
    # 编辑文档元数据和版本，以及删除文档。
    KNOWLEDGE_DOCUMENT_MANAGE = "knowledge:document:manage"
    # 提交索引、重新索引或重试失败的索引任务。
    KNOWLEDGE_DOCUMENT_INDEX = "knowledge:document:index"

    # 发起基于知识库检索结果并带引用依据的问答。
    KNOWLEDGE_CHAT_USE = "knowledge:chat:use"
    # 独立审计项目内其他用户的会话与消息，不授予发送、修改和删除权限。
    KNOWLEDGE_CHAT_AUDIT = "knowledge:chat:audit"

    # 查看项目内的需求、需求版本和原子需求点。
    REQUIREMENT_VIEW = "requirement:view"
    # 创建、编辑和删除需求，以及人工维护需求点。
    REQUIREMENT_MANAGE = "requirement:manage"
    # 启动 AI 需求拆解或重试失败的拆解任务。
    REQUIREMENT_EXTRACT = "requirement:extract"

    # 查看项目内的测试用例、步骤和需求覆盖关系。
    TEST_CASE_VIEW = "test:case:view"
    # 创建、编辑、删除测试用例及其步骤。
    TEST_CASE_MANAGE = "test:case:manage"
    # 启动历史用例检索、覆盖分析和缺失用例生成。
    TEST_CASE_GENERATE = "test:case:generate"
    # 接受、修改、驳回、判重和发布 AI 生成的测试用例。
    TEST_CASE_REVIEW = "test:case:review"

    # 查看通知渠道及脱敏后的配置。
    NOTIFICATION_VIEW = "notification:view"
    # 新增通知渠道。
    NOTIFICATION_CREATE = "notification:create"
    # 编辑通知渠道配置及密钥。
    NOTIFICATION_UPDATE = "notification:update"
    # 删除通知渠道。
    NOTIFICATION_DELETE = "notification:delete"
    # 使用通知渠道发送测试消息。
    NOTIFICATION_TEST = "notification:test"

    # 查看工具目录、外部连接、任务、审批、日志和产物。
    TOOL_VIEW = "tool:view"
    # 创建和编辑外部连接、文件模板及低风险工具任务。
    TOOL_MANAGE = "tool:manage"
    # 发起工具预览；Agent 也只能调用这个权限对应的只读阶段。
    TOOL_PREVIEW = "tool:preview"
    # 执行已经满足审批条件的工具任务。
    TOOL_EXECUTE = "tool:execute"
    # 审批或驳回中高风险工具任务。
    TOOL_APPROVE = "tool:approve"
    # 使用可回滚任务保存的备份执行回滚。
    TOOL_ROLLBACK = "tool:rollback"
    # 查看未经精简的工具审计信息；敏感凭据正文仍不会返回。
    TOOL_AUDIT = "tool:audit"

    # 查看项目内 Supervisor 运行列表、计划步骤和脱敏执行结果。
    SUPERVISOR_VIEW = "supervisor:view"
    # 创建 Supervisor 规划以及取消本人或有权管理的未执行运行。
    SUPERVISOR_RUN = "supervisor:run"
    # 审批或驳回 Supervisor 中高风险步骤；与创建计划权限分离，避免发起人自批。
    SUPERVISOR_APPROVE = "supervisor:approve"

    # MCP 管理页与页面内受控试调用；真正工具调用还会再次检查每项业务权限。
    MCP_VIEW = "mcp:view"
    MCP_INVOKE = "mcp:invoke"

    # 查看系统用户列表和详情。
    SYSTEM_USER_VIEW = "system:user:view"
    # 创建系统用户。
    SYSTEM_USER_CREATE = "system:user:create"
    # 编辑用户资料、状态和角色。
    SYSTEM_USER_UPDATE = "system:user:update"
    # 删除系统用户。
    SYSTEM_USER_DELETE = "system:user:delete"

    # 查看角色及其菜单权限。
    SYSTEM_ROLE_VIEW = "system:role:view"
    # 创建角色。
    SYSTEM_ROLE_CREATE = "system:role:create"
    # 编辑角色信息和菜单权限。
    SYSTEM_ROLE_UPDATE = "system:role:update"
    # 删除非系统内置角色。
    SYSTEM_ROLE_DELETE = "system:role:delete"

    # 查看目录、页面和按钮菜单树。
    SYSTEM_MENU_VIEW = "system:menu:view"
    # 创建目录、页面或按钮菜单。
    SYSTEM_MENU_CREATE = "system:menu:create"
    # 编辑菜单路由、显示信息或权限码。
    SYSTEM_MENU_UPDATE = "system:menu:update"
    # 删除允许移除的菜单节点。
    SYSTEM_MENU_DELETE = "system:menu:delete"

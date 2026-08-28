-- 需求分析与用例生成主线基础表。
-- 执行前请先确认当前数据库中不存在同名业务表；本文件不会删除或覆盖已有表。

CREATE TABLE IF NOT EXISTS requirements (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES test_projects(id) ON DELETE CASCADE,
    module_id INTEGER REFERENCES test_modules(id) ON DELETE SET NULL,
    document_id INTEGER REFERENCES knowledge_documents(id) ON DELETE SET NULL,
    title VARCHAR(300) NOT NULL,
    version VARCHAR(40) NOT NULL DEFAULT '1.0',
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    source_url VARCHAR(1000),
    summary TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT chk_requirements_status CHECK (
        status IN ('DRAFT', 'EXTRACTING', 'REVIEWING', 'CONFIRMED', 'FAILED', 'ARCHIVED')
    )
);

CREATE INDEX IF NOT EXISTS ix_requirements_project_status
    ON requirements(project_id, status);
CREATE INDEX IF NOT EXISTS ix_requirements_module_id
    ON requirements(module_id);

COMMENT ON TABLE requirements IS '项目需求及其版本、来源和拆解状态';
COMMENT ON COLUMN requirements.id IS '需求主键';
COMMENT ON COLUMN requirements.project_id IS '所属测试项目 ID，是需求数据权限边界';
COMMENT ON COLUMN requirements.module_id IS '可选的所属功能模块 ID';
COMMENT ON COLUMN requirements.document_id IS '关联的原始知识文档 ID，用于读取需求正文和定位证据';
COMMENT ON COLUMN requirements.title IS '需求标题';
COMMENT ON COLUMN requirements.version IS '需求版本标识，例如 1.0、1.1 或 2026.08';
COMMENT ON COLUMN requirements.status IS '需求状态：DRAFT/EXTRACTING/REVIEWING/CONFIRMED/FAILED/ARCHIVED';
COMMENT ON COLUMN requirements.source_url IS '可选的外部需求来源地址';
COMMENT ON COLUMN requirements.summary IS '需求正文的简要说明或 AI 提取摘要';
COMMENT ON COLUMN requirements.metadata IS '需求扩展信息，使用 JSON 保存不固定的业务字段';
COMMENT ON COLUMN requirements.created_by IS '创建需求的用户 ID';
COMMENT ON COLUMN requirements.created_at IS '创建时间';
COMMENT ON COLUMN requirements.updated_at IS '更新时间';
COMMENT ON COLUMN requirements.deleted_at IS '软删除时间；为空表示需求仍有效';

CREATE TABLE IF NOT EXISTS requirement_items (
    id SERIAL PRIMARY KEY,
    requirement_id INTEGER NOT NULL REFERENCES requirements(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES requirement_items(id) ON DELETE CASCADE,
    item_code VARCHAR(80),
    title VARCHAR(300) NOT NULL,
    description TEXT NOT NULL,
    item_type VARCHAR(30) NOT NULL DEFAULT 'FUNCTIONAL',
    priority VARCHAR(10) NOT NULL DEFAULT 'P2',
    acceptance_criteria TEXT NOT NULL DEFAULT '',
    source_locator JSONB NOT NULL DEFAULT '{}'::jsonb,
    ai_generated BOOLEAN NOT NULL DEFAULT TRUE,
    confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    order_no INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_requirement_items_requirement_code UNIQUE (requirement_id, item_code),
    CONSTRAINT chk_requirement_items_not_self_parent CHECK (parent_id IS NULL OR parent_id <> id),
    CONSTRAINT chk_requirement_items_type CHECK (
        item_type IN (
            'FUNCTIONAL', 'BUSINESS_RULE', 'NORMAL_FLOW', 'EXCEPTION_FLOW',
            'BOUNDARY', 'PERMISSION', 'PERFORMANCE', 'SECURITY', 'COMPATIBILITY', 'OTHER'
        )
    ),
    CONSTRAINT chk_requirement_items_priority CHECK (priority IN ('P0', 'P1', 'P2', 'P3'))
);

CREATE INDEX IF NOT EXISTS ix_requirement_items_requirement_parent
    ON requirement_items(requirement_id, parent_id);
CREATE INDEX IF NOT EXISTS ix_requirement_items_requirement_confirmed
    ON requirement_items(requirement_id, confirmed);

COMMENT ON TABLE requirement_items IS '需求拆解后可人工校正和确认的原子需求点';
COMMENT ON COLUMN requirement_items.id IS '原子需求点主键';
COMMENT ON COLUMN requirement_items.requirement_id IS '所属需求 ID';
COMMENT ON COLUMN requirement_items.parent_id IS '可选的父需求点 ID，用于组织层级结构';
COMMENT ON COLUMN requirement_items.item_code IS '需求内唯一的需求点编码';
COMMENT ON COLUMN requirement_items.title IS '原子需求点标题';
COMMENT ON COLUMN requirement_items.description IS '原子需求点完整说明';
COMMENT ON COLUMN requirement_items.item_type IS '功能、角色、规则、流程、边界或验收条件等类型';
COMMENT ON COLUMN requirement_items.priority IS '需求点优先级，P0 最高、P3 最低';
COMMENT ON COLUMN requirement_items.acceptance_criteria IS '判断该需求点是否实现的验收条件';
COMMENT ON COLUMN requirement_items.source_locator IS '原文定位信息，例如页码、章节和切片 ID';
COMMENT ON COLUMN requirement_items.ai_generated IS '是否由 AI 自动提取';
COMMENT ON COLUMN requirement_items.confirmed IS '是否已由测试人员人工确认';
COMMENT ON COLUMN requirement_items.order_no IS '需求点在同一需求中的显示顺序，数值越小越靠前';
COMMENT ON COLUMN requirement_items.created_at IS '创建时间';
COMMENT ON COLUMN requirement_items.updated_at IS '更新时间';

CREATE TABLE IF NOT EXISTS requirement_extraction_tasks (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES test_projects(id) ON DELETE CASCADE,
    requirement_id INTEGER NOT NULL REFERENCES requirements(id) ON DELETE CASCADE,
    celery_task_id VARCHAR(50) NOT NULL UNIQUE,
    model_id INTEGER REFERENCES ai_models(id) ON DELETE SET NULL,
    prompt_template_id INTEGER REFERENCES prompt_templates(id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    progress INTEGER NOT NULL DEFAULT 0,
    current_stage VARCHAR(40) NOT NULL DEFAULT 'QUEUED',
    input_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    requested_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_requirement_extraction_tasks_status CHECK (
        status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')
    ),
    CONSTRAINT chk_requirement_extraction_tasks_progress CHECK (
        progress >= 0 AND progress <= 100
    )
);

CREATE INDEX IF NOT EXISTS ix_requirement_extraction_tasks_project_status
    ON requirement_extraction_tasks(project_id, status);
CREATE INDEX IF NOT EXISTS ix_requirement_extraction_tasks_requirement_created
    ON requirement_extraction_tasks(requirement_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_requirement_extraction_tasks_active_requirement
    ON requirement_extraction_tasks(requirement_id)
    WHERE status IN ('PENDING', 'RUNNING', 'WAITING_REVIEW');

COMMENT ON TABLE requirement_extraction_tasks IS 'AI 需求拆解任务的执行进度、输入输出快照和失败审计';
COMMENT ON COLUMN requirement_extraction_tasks.id IS '需求拆解任务主键';
COMMENT ON COLUMN requirement_extraction_tasks.project_id IS '所属测试项目 ID，也是任务的数据权限边界';
COMMENT ON COLUMN requirement_extraction_tasks.requirement_id IS '本次需要拆解的需求 ID';
COMMENT ON COLUMN requirement_extraction_tasks.celery_task_id IS 'Celery 任务 ID，用于关联消息队列中的实际任务';
COMMENT ON COLUMN requirement_extraction_tasks.model_id IS '本次实际调用的 AI 模型 ID';
COMMENT ON COLUMN requirement_extraction_tasks.prompt_template_id IS '本次实际使用的需求拆解 Prompt 模板 ID';
COMMENT ON COLUMN requirement_extraction_tasks.status IS '任务状态：PENDING/RUNNING/COMPLETED/FAILED/CANCELLED';
COMMENT ON COLUMN requirement_extraction_tasks.progress IS '任务完成百分比，范围为 0 到 100';
COMMENT ON COLUMN requirement_extraction_tasks.current_stage IS '当前业务阶段，例如读取文档、调用模型或保存需求点';
COMMENT ON COLUMN requirement_extraction_tasks.input_snapshot IS '任务提交时的需求版本、文档和执行参数快照';
COMMENT ON COLUMN requirement_extraction_tasks.output_snapshot IS '模型原始结构化结果和最终保存数量等输出快照';
COMMENT ON COLUMN requirement_extraction_tasks.error_message IS '任务失败时经过脱敏和截断的错误摘要';
COMMENT ON COLUMN requirement_extraction_tasks.requested_by IS '发起本次需求拆解的用户 ID';
COMMENT ON COLUMN requirement_extraction_tasks.started_at IS 'Worker 真正开始执行任务的时间';
COMMENT ON COLUMN requirement_extraction_tasks.finished_at IS '任务成功、失败或取消的结束时间';
COMMENT ON COLUMN requirement_extraction_tasks.created_at IS '任务记录创建时间';
COMMENT ON COLUMN requirement_extraction_tasks.updated_at IS '任务记录最近更新时间';

CREATE TABLE IF NOT EXISTS test_cases (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES test_projects(id) ON DELETE CASCADE,
    module_id INTEGER REFERENCES test_modules(id) ON DELETE SET NULL,
    case_code VARCHAR(80),
    title VARCHAR(300) NOT NULL,
    case_type VARCHAR(30) NOT NULL DEFAULT 'FUNCTIONAL',
    priority VARCHAR(10) NOT NULL DEFAULT 'P2',
    preconditions TEXT NOT NULL DEFAULT '',
    expected_summary TEXT NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    source VARCHAR(20) NOT NULL DEFAULT 'MANUAL',
    automatable BOOLEAN NOT NULL DEFAULT FALSE,
    version INTEGER NOT NULL DEFAULT 1,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT uq_test_cases_project_code UNIQUE (project_id, case_code),
    CONSTRAINT chk_test_cases_version CHECK (version > 0),
    CONSTRAINT chk_test_cases_type CHECK (
        case_type IN ('FUNCTIONAL', 'API', 'UI', 'PERFORMANCE', 'SECURITY', 'COMPATIBILITY', 'REGRESSION', 'SMOKE', 'OTHER')
    ),
    CONSTRAINT chk_test_cases_priority CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),
    CONSTRAINT chk_test_cases_status CHECK (
        status IN ('DRAFT', 'REVIEWING', 'APPROVED', 'REJECTED', 'PUBLISHED', 'DISABLED')
    ),
    CONSTRAINT chk_test_cases_source CHECK (source IN ('MANUAL', 'AI_GENERATED', 'IMPORTED'))
);

CREATE INDEX IF NOT EXISTS ix_test_cases_project_status
    ON test_cases(project_id, status);
CREATE INDEX IF NOT EXISTS ix_test_cases_module_id
    ON test_cases(module_id);

COMMENT ON TABLE test_cases IS '项目内可版本追踪、可审核发布的测试用例';
COMMENT ON COLUMN test_cases.id IS '测试用例主键';
COMMENT ON COLUMN test_cases.project_id IS '所属测试项目 ID';
COMMENT ON COLUMN test_cases.module_id IS '可选的所属功能模块 ID';
COMMENT ON COLUMN test_cases.case_code IS '项目内的用例编码';
COMMENT ON COLUMN test_cases.title IS '测试用例标题';
COMMENT ON COLUMN test_cases.case_type IS '功能、接口、UI、性能、安全或兼容性测试';
COMMENT ON COLUMN test_cases.priority IS '用例优先级';
COMMENT ON COLUMN test_cases.preconditions IS '执行用例前必须满足的条件';
COMMENT ON COLUMN test_cases.expected_summary IS '整条用例的总体预期结果';
COMMENT ON COLUMN test_cases.status IS '用例审核发布状态';
COMMENT ON COLUMN test_cases.source IS '用例来源：人工、AI 或导入';
COMMENT ON COLUMN test_cases.automatable IS '是否适合转换为自动化定义';
COMMENT ON COLUMN test_cases.version IS '测试用例版本号';
COMMENT ON COLUMN test_cases.metadata IS '测试用例扩展信息，例如生成配置和业务标签';
COMMENT ON COLUMN test_cases.created_by IS '创建用例的用户 ID';
COMMENT ON COLUMN test_cases.updated_by IS '最后编辑用例的用户 ID';
COMMENT ON COLUMN test_cases.created_at IS '创建时间';
COMMENT ON COLUMN test_cases.updated_at IS '更新时间';
COMMENT ON COLUMN test_cases.deleted_at IS '软删除时间；为空表示用例仍有效';

CREATE TABLE IF NOT EXISTS test_case_steps (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    step_no INTEGER NOT NULL,
    action TEXT NOT NULL,
    test_data JSONB,
    expected_result TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_test_case_steps_case_no UNIQUE (test_case_id, step_no),
    CONSTRAINT chk_test_case_steps_no CHECK (step_no > 0)
);

COMMENT ON TABLE test_case_steps IS '测试用例的结构化操作步骤和预期结果';
COMMENT ON COLUMN test_case_steps.id IS '用例步骤主键';
COMMENT ON COLUMN test_case_steps.test_case_id IS '所属测试用例 ID';
COMMENT ON COLUMN test_case_steps.step_no IS '步骤序号，从 1 开始';
COMMENT ON COLUMN test_case_steps.action IS '本步骤执行的操作';
COMMENT ON COLUMN test_case_steps.test_data IS '本步骤使用的测试数据';
COMMENT ON COLUMN test_case_steps.expected_result IS '本步骤预期结果';
COMMENT ON COLUMN test_case_steps.created_at IS '创建时间';
COMMENT ON COLUMN test_case_steps.updated_at IS '更新时间';

CREATE TABLE IF NOT EXISTS requirement_case_links (
    requirement_item_id INTEGER NOT NULL REFERENCES requirement_items(id) ON DELETE CASCADE,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    coverage_type VARCHAR(20) NOT NULL,
    confidence NUMERIC(5, 4),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (requirement_item_id, test_case_id),
    CONSTRAINT chk_requirement_case_links_coverage CHECK (coverage_type IN ('FULL', 'PARTIAL')),
    CONSTRAINT chk_requirement_case_links_confidence CHECK (confidence >= 0 AND confidence <= 1)
);

CREATE INDEX IF NOT EXISTS ix_requirement_case_links_case_id
    ON requirement_case_links(test_case_id);

COMMENT ON TABLE requirement_case_links IS '需求点与测试用例的覆盖矩阵；没有记录表示未覆盖';
COMMENT ON COLUMN requirement_case_links.requirement_item_id IS '被覆盖的原子需求点 ID';
COMMENT ON COLUMN requirement_case_links.test_case_id IS '提供覆盖的测试用例 ID';
COMMENT ON COLUMN requirement_case_links.coverage_type IS '完全覆盖 FULL 或部分覆盖 PARTIAL';
COMMENT ON COLUMN requirement_case_links.confidence IS 'AI 判断覆盖关系的置信度，范围 0 到 1';
COMMENT ON COLUMN requirement_case_links.evidence IS '覆盖判断所依据的步骤、规则和引用快照';
COMMENT ON COLUMN requirement_case_links.created_by IS '建立或确认覆盖关系的用户 ID';
COMMENT ON COLUMN requirement_case_links.created_at IS '创建时间';

CREATE TABLE IF NOT EXISTS case_generation_tasks (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES test_projects(id) ON DELETE CASCADE,
    requirement_id INTEGER NOT NULL REFERENCES requirements(id) ON DELETE CASCADE,
    model_id INTEGER REFERENCES ai_models(id) ON DELETE SET NULL,
    prompt_template_id INTEGER REFERENCES prompt_templates(id) ON DELETE SET NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    input_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    retrieval_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    progress INTEGER NOT NULL DEFAULT 0,
    current_stage VARCHAR(80),
    error_message TEXT,
    requested_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_case_generation_tasks_status CHECK (
        status IN ('PENDING', 'RUNNING', 'WAITING_REVIEW', 'COMPLETED', 'FAILED', 'CANCELLED')
    ),
    CONSTRAINT chk_case_generation_tasks_progress CHECK (progress >= 0 AND progress <= 100)
);

CREATE INDEX IF NOT EXISTS ix_case_generation_tasks_project_status
    ON case_generation_tasks(project_id, status);

-- Redis/Celery 是至少一次投递，同一需求在排队或执行阶段只能存在一个活动任务。
-- 部分唯一索引约束排队、执行和待审核阶段，不影响已完成历史和后续重新生成。
CREATE UNIQUE INDEX IF NOT EXISTS uq_case_generation_tasks_active_requirement
    ON case_generation_tasks(requirement_id)
    WHERE status IN ('PENDING', 'RUNNING');

COMMENT ON TABLE case_generation_tasks IS '覆盖分析和缺失用例生成任务的输入、检索及输出快照';
COMMENT ON COLUMN case_generation_tasks.id IS '生成任务主键';
COMMENT ON COLUMN case_generation_tasks.project_id IS '所属测试项目 ID';
COMMENT ON COLUMN case_generation_tasks.requirement_id IS '本次分析的需求 ID';
COMMENT ON COLUMN case_generation_tasks.model_id IS '实际使用的生成模型 ID';
COMMENT ON COLUMN case_generation_tasks.prompt_template_id IS '实际使用的 Prompt 模板 ID';
COMMENT ON COLUMN case_generation_tasks.status IS '生成任务状态';
COMMENT ON COLUMN case_generation_tasks.input_snapshot IS '提交给工作流的需求和配置快照';
COMMENT ON COLUMN case_generation_tasks.output_snapshot IS '模型结构化输出和质量检查结果快照';
COMMENT ON COLUMN case_generation_tasks.retrieval_snapshot IS '检索到的历史用例及其分数快照';
COMMENT ON COLUMN case_generation_tasks.progress IS '任务进度百分比，范围 0 到 100';
COMMENT ON COLUMN case_generation_tasks.current_stage IS '任务当前执行阶段，供前端展示进度说明';
COMMENT ON COLUMN case_generation_tasks.error_message IS '任务失败时的脱敏错误摘要';
COMMENT ON COLUMN case_generation_tasks.requested_by IS '发起生成任务的用户 ID';
COMMENT ON COLUMN case_generation_tasks.started_at IS '任务开始执行时间';
COMMENT ON COLUMN case_generation_tasks.finished_at IS '任务完成、失败或取消的时间';
COMMENT ON COLUMN case_generation_tasks.created_at IS '创建时间';
COMMENT ON COLUMN case_generation_tasks.updated_at IS '更新时间';

CREATE TABLE IF NOT EXISTS case_review_records (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    generation_task_id INTEGER REFERENCES case_generation_tasks(id) ON DELETE SET NULL,
    reviewer_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(20) NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    before_data JSONB,
    after_data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_case_review_records_action CHECK (
        action IN ('SUBMIT', 'ACCEPT', 'MODIFY', 'REJECT', 'DUPLICATE', 'PUBLISH', 'DISABLE')
    )
);

CREATE INDEX IF NOT EXISTS ix_case_review_records_case_created
    ON case_review_records(test_case_id, created_at);

COMMENT ON TABLE case_review_records IS 'AI 生成用例的接受、修改、驳回、判重和发布审计记录';
COMMENT ON COLUMN case_review_records.id IS '审核记录主键';
COMMENT ON COLUMN case_review_records.test_case_id IS '被审核的测试用例 ID';
COMMENT ON COLUMN case_review_records.generation_task_id IS '产生该用例的生成任务 ID';
COMMENT ON COLUMN case_review_records.reviewer_id IS '执行审核动作的用户 ID';
COMMENT ON COLUMN case_review_records.action IS '接受、修改、驳回、判重或发布动作';
COMMENT ON COLUMN case_review_records.comment IS '审核意见';
COMMENT ON COLUMN case_review_records.before_data IS '审核动作前的用例快照';
COMMENT ON COLUMN case_review_records.after_data IS '审核动作后的用例快照';
COMMENT ON COLUMN case_review_records.created_at IS '创建时间';

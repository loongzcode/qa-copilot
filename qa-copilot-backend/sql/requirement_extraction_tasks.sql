-- FR-REQ-002：AI 需求拆解任务审计表。
-- 该脚本可重复执行；只负责新增任务表，不会修改或删除现有需求数据。

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
    WHERE status IN ('PENDING', 'RUNNING');

COMMENT ON TABLE requirement_extraction_tasks IS
    'AI 需求拆解任务的执行进度、输入输出快照和失败审计';
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

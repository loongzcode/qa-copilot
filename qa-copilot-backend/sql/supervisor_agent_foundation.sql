BEGIN;

CREATE TABLE IF NOT EXISTS supervisor_runs (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES test_projects(id) ON DELETE CASCADE,
    goal TEXT NOT NULL,
    invocation_source VARCHAR(20) NOT NULL DEFAULT 'SUPERVISOR'
        CHECK (invocation_source IN ('SUPERVISOR','MCP')),
    status VARCHAR(30) NOT NULL DEFAULT 'PLANNING'
        CHECK (status IN ('PLANNING','PLAN_REJECTED','READY','WAITING_APPROVAL','RUNNING','SUCCEEDED','FAILED','CANCELLED')),
    current_step_no INTEGER NOT NULL DEFAULT 0 CHECK (current_step_no >= 0),
    plan_version INTEGER NOT NULL DEFAULT 1,
    model_id INTEGER REFERENCES ai_models(id) ON DELETE SET NULL,
    requested_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    permission_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
    context_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_supervisor_runs_project_status ON supervisor_runs(project_id, status, id);
CREATE INDEX IF NOT EXISTS ix_supervisor_runs_requester_created ON supervisor_runs(requested_by, created_at);

CREATE TABLE IF NOT EXISTS supervisor_plan_steps (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES supervisor_runs(id) ON DELETE CASCADE,
    step_no INTEGER NOT NULL CHECK (step_no > 0),
    step_key VARCHAR(64) NOT NULL,
    capability_code VARCHAR(120) NOT NULL,
    purpose TEXT NOT NULL,
    arguments_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    depends_on JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_permission VARCHAR(120) NOT NULL,
    risk_level VARCHAR(20) NOT NULL CHECK (risk_level IN ('LOW','MEDIUM','HIGH')),
    decision VARCHAR(30) NOT NULL CHECK (decision IN ('READY','BLOCKED_APPROVAL','REJECTED')),
    requires_human_approval BOOLEAN NOT NULL DEFAULT false,
    status VARCHAR(30) NOT NULL DEFAULT 'PROPOSED'
        CHECK (status IN ('PROPOSED','REJECTED','READY','WAITING_APPROVAL','RUNNING','SUCCEEDED','FAILED','SKIPPED','CANCELLED')),
    tool_task_id INTEGER REFERENCES tool_tasks(id) ON DELETE SET NULL,
    result_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_supervisor_plan_steps_run_no UNIQUE (run_id, step_no),
    CONSTRAINT uq_supervisor_plan_steps_run_key UNIQUE (run_id, step_key)
);
CREATE INDEX IF NOT EXISTS ix_supervisor_plan_steps_run_status
    ON supervisor_plan_steps(run_id, status, step_no);

COMMENT ON TABLE supervisor_runs IS 'Supervisor 开放目标、规划状态和执行结果主记录';
COMMENT ON TABLE supervisor_plan_steps IS 'Supervisor 计划中可独立审批和执行的步骤';

COMMENT ON COLUMN supervisor_runs.permission_snapshot IS '规划时权限快照；执行前仍重新校验实时权限';
COMMENT ON COLUMN supervisor_runs.context_snapshot IS '规划所依据的业务对象 ID 和脱敏上下文';
COMMENT ON COLUMN supervisor_plan_steps.arguments_snapshot IS '校验后的脱敏调用参数快照';
COMMENT ON COLUMN supervisor_plan_steps.tool_task_id IS '中高风险步骤关联的现有工具审批任务';

COMMIT;

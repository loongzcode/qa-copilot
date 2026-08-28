BEGIN;

-- Supervisor 主运行心跳与有限恢复计数。
ALTER TABLE supervisor_runs
    ADD COLUMN IF NOT EXISTS execution_heartbeat_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS execution_recovery_count INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN supervisor_runs.execution_heartbeat_at IS
    '执行 Worker 最近一次推进步骤的时间，用于识别失联任务';
COMMENT ON COLUMN supervisor_runs.execution_recovery_count IS
    '执行任务因 Worker 失联而重新入队的次数';

-- 审批结果直接绑定计划步骤：每个计划版本的一步只允许作出一次最终决定。
ALTER TABLE supervisor_plan_steps
    ADD COLUMN IF NOT EXISTS approval_decided_by INTEGER,
    ADD COLUMN IF NOT EXISTS approval_decision VARCHAR(20),
    ADD COLUMN IF NOT EXISTS approval_comment TEXT,
    ADD COLUMN IF NOT EXISTS approval_decided_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_supervisor_steps_approval_user'
    ) THEN
        ALTER TABLE supervisor_plan_steps
            ADD CONSTRAINT fk_supervisor_steps_approval_user
            FOREIGN KEY (approval_decided_by) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_supervisor_steps_approval_decision'
    ) THEN
        ALTER TABLE supervisor_plan_steps
            ADD CONSTRAINT chk_supervisor_steps_approval_decision
            CHECK (approval_decision IS NULL OR approval_decision IN ('APPROVED', 'REJECTED'));
    END IF;
END $$;

COMMENT ON COLUMN supervisor_plan_steps.approval_decided_by IS '批准或驳回该步骤的用户 ID';
COMMENT ON COLUMN supervisor_plan_steps.approval_decision IS '人工审批决定：APPROVED 或 REJECTED';
COMMENT ON COLUMN supervisor_plan_steps.approval_comment IS '审批意见';
COMMENT ON COLUMN supervisor_plan_steps.approval_decided_at IS '人工作出审批决定的时间';

-- Supervisor 写能力使用步骤主键作为幂等键，重复 Celery 消息只能复用同一生成任务。
ALTER TABLE case_generation_tasks
    ADD COLUMN IF NOT EXISTS supervisor_step_id INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_case_generation_supervisor_step'
    ) THEN
        ALTER TABLE case_generation_tasks
            ADD CONSTRAINT fk_case_generation_supervisor_step
            FOREIGN KEY (supervisor_step_id) REFERENCES supervisor_plan_steps(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_case_generation_tasks_supervisor_step
    ON case_generation_tasks(supervisor_step_id)
    WHERE supervisor_step_id IS NOT NULL;

COMMENT ON COLUMN case_generation_tasks.supervisor_step_id IS
    '由 Supervisor 写能力触发时的步骤 ID；用于重复消息幂等复用同一任务';

COMMIT;

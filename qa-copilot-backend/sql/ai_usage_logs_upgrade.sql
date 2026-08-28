BEGIN;

-- 调用链、用户、项目和异步任务关联。
ALTER TABLE ai_usage_logs
    ADD COLUMN IF NOT EXISTS request_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS task_id VARCHAR(128),
    ADD COLUMN IF NOT EXISTS user_id INTEGER,
    ADD COLUMN IF NOT EXISTS project_id INTEGER,
    ADD COLUMN IF NOT EXISTS provider_name VARCHAR(100),
    ADD COLUMN IF NOT EXISTS model_name VARCHAR(100),
    ADD COLUMN IF NOT EXISTS retrieval_hit_count INTEGER NOT NULL DEFAULT 0;

-- 使用当前仍存在的配置为历史日志补齐服务商、模型名称快照。
UPDATE ai_usage_logs AS usage_log
SET provider_name = provider.name
FROM ai_providers AS provider
WHERE usage_log.provider_id = provider.id
  AND usage_log.provider_name IS NULL;

UPDATE ai_usage_logs AS usage_log
SET model_name = model.name
FROM ai_models AS model
WHERE usage_log.model_id = model.id
  AND usage_log.model_name IS NULL;

-- 理论上旧外键会阻止配置被提前删除；这里仍提供兜底文字，保证迁移可完成。
UPDATE ai_usage_logs
SET provider_name = '已删除服务商'
WHERE provider_name IS NULL;

UPDATE ai_usage_logs
SET model_name = '已删除模型'
WHERE model_name IS NULL;

ALTER TABLE ai_usage_logs
    ALTER COLUMN provider_name SET NOT NULL,
    ALTER COLUMN model_name SET NOT NULL,
    ALTER COLUMN provider_id DROP NOT NULL,
    ALTER COLUMN model_id DROP NOT NULL;

-- 删除旧外键，改成配置删除时仅清空外键、保留历史日志。
ALTER TABLE ai_usage_logs
    DROP CONSTRAINT IF EXISTS ai_usage_logs_provider_id_fkey,
    DROP CONSTRAINT IF EXISTS ai_usage_logs_model_id_fkey;

ALTER TABLE ai_usage_logs
    ADD CONSTRAINT ai_usage_logs_provider_id_fkey
        FOREIGN KEY (provider_id)
        REFERENCES ai_providers (id)
        ON DELETE SET NULL,
    ADD CONSTRAINT ai_usage_logs_model_id_fkey
        FOREIGN KEY (model_id)
        REFERENCES ai_models (id)
        ON DELETE SET NULL;

-- 这些外键关联只用于审计定位；用户或项目删除后日志仍然保留。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ai_usage_logs_user_id_fkey'
    ) THEN
        ALTER TABLE ai_usage_logs
            ADD CONSTRAINT ai_usage_logs_user_id_fkey
                FOREIGN KEY (user_id)
                REFERENCES users (id)
                ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ai_usage_logs_project_id_fkey'
    ) THEN
        ALTER TABLE ai_usage_logs
            ADD CONSTRAINT ai_usage_logs_project_id_fkey
                FOREIGN KEY (project_id)
                REFERENCES test_projects (id)
                ON DELETE SET NULL;
    END IF;
END
$$;

-- 数据合法性约束重复执行时不再创建。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_ai_usage_logs_status'
    ) THEN
        ALTER TABLE ai_usage_logs
            ADD CONSTRAINT chk_ai_usage_logs_status
                CHECK (status IN ('success', 'failed'));
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_ai_usage_logs_non_negative_metrics'
    ) THEN
        ALTER TABLE ai_usage_logs
            ADD CONSTRAINT chk_ai_usage_logs_non_negative_metrics
                CHECK (
                    input_tokens >= 0
                    AND output_tokens >= 0
                    AND total_tokens >= 0
                    AND latency_ms >= 0
                    AND retrieval_hit_count >= 0
                );
    END IF;
END
$$;

-- 列表默认按时间倒序，其他组合索引服务于常用筛选条件。
CREATE INDEX IF NOT EXISTS ix_ai_usage_logs_created_at
    ON ai_usage_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_usage_logs_status_created_at
    ON ai_usage_logs (status, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_usage_logs_provider_created_at
    ON ai_usage_logs (provider_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_usage_logs_model_created_at
    ON ai_usage_logs (model_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_usage_logs_task_type_created_at
    ON ai_usage_logs (task_type, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_usage_logs_user_created_at
    ON ai_usage_logs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_usage_logs_project_created_at
    ON ai_usage_logs (project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_usage_logs_request_id
    ON ai_usage_logs (request_id)
    WHERE request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_ai_usage_logs_task_id
    ON ai_usage_logs (task_id)
    WHERE task_id IS NOT NULL;

COMMENT ON TABLE ai_usage_logs IS
    'AI 调用审计日志，记录调用身份、模型、Token、耗时和脱敏后的失败原因';
COMMENT ON COLUMN ai_usage_logs.id IS '调用日志主键';
COMMENT ON COLUMN ai_usage_logs.request_id IS
    'HTTP 请求追踪标识，同一次请求链路中的调用保持一致';
COMMENT ON COLUMN ai_usage_logs.task_id IS
    'Celery 任务、生成批次或其他业务任务标识';
COMMENT ON COLUMN ai_usage_logs.user_id IS
    '发起调用的用户主键，后台任务没有明确用户时为空';
COMMENT ON COLUMN ai_usage_logs.project_id IS
    '调用所属项目主键，系统级调用时为空';
COMMENT ON COLUMN ai_usage_logs.provider_id IS
    'AI 服务商配置主键，配置删除后自动置空';
COMMENT ON COLUMN ai_usage_logs.model_id IS
    'AI 模型配置主键，配置删除后自动置空';
COMMENT ON COLUMN ai_usage_logs.provider_name IS
    '调用发生时的服务商名称快照';
COMMENT ON COLUMN ai_usage_logs.model_name IS
    '调用发生时的平台模型名称快照';
COMMENT ON COLUMN ai_usage_logs.task_type IS
    '调用用途，例如 embedding、rerank、knowledge_qa 或 query_rewrite';
COMMENT ON COLUMN ai_usage_logs.status IS
    '调用结果状态：success 或 failed';
COMMENT ON COLUMN ai_usage_logs.input_tokens IS '输入 Token 数';
COMMENT ON COLUMN ai_usage_logs.output_tokens IS '输出 Token 数';
COMMENT ON COLUMN ai_usage_logs.total_tokens IS '输入和输出的总 Token 数';
COMMENT ON COLUMN ai_usage_logs.latency_ms IS '模型调用耗时，单位为毫秒';
COMMENT ON COLUMN ai_usage_logs.retrieval_hit_count IS
    '知识检索最终命中的资料数量，非检索任务为 0';
COMMENT ON COLUMN ai_usage_logs.error_message IS
    '调用失败时保存的脱敏异常摘要';
COMMENT ON COLUMN ai_usage_logs.created_at IS '调用发生时间';

COMMIT;

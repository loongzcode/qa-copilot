-- 事务性发件箱：把“需要发布 Celery 消息”与业务状态保存在同一个 PostgreSQL 事务中。
-- 本脚本只创建通用发件箱表；不会修改现有知识文档数据，也不会自动发送任务。

CREATE TABLE IF NOT EXISTS outbox_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(80) NOT NULL,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id BIGINT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 10,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_at TIMESTAMPTZ,
    locked_by VARCHAR(160),
    published_at TIMESTAMPTZ,
    broker_task_id VARCHAR(80),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_outbox_events_status CHECK (
        status IN ('PENDING', 'PROCESSING', 'RETRY', 'PUBLISHED', 'FAILED')
    ),
    CONSTRAINT chk_outbox_events_attempts CHECK (
        attempt_count >= 0 AND max_attempts > 0
    )
);

-- 兼容已经执行过早期版本脚本的开发数据库。
ALTER TABLE outbox_events
    ADD COLUMN IF NOT EXISTS broker_task_id VARCHAR(80);

-- 支持发布器按“可发送状态 + 到期时间”快速领取一批事件。
CREATE INDEX IF NOT EXISTS ix_outbox_events_dispatch
    ON outbox_events(status, available_at, id);

-- 同一业务对象不能同时存在多条活动事件；已完成历史不会阻止以后重新索引。
CREATE UNIQUE INDEX IF NOT EXISTS uq_outbox_events_active_aggregate
    ON outbox_events(event_type, aggregate_type, aggregate_id)
    WHERE status IN ('PENDING', 'PROCESSING', 'RETRY');

COMMENT ON TABLE outbox_events IS '需要可靠发布到 Celery 的事务性发件箱事件';
COMMENT ON COLUMN outbox_events.id IS '发件箱事件主键，也可作为消息幂等标识';
COMMENT ON COLUMN outbox_events.event_type IS '事件类型，发布器据此选择要调用的 Celery 任务';
COMMENT ON COLUMN outbox_events.aggregate_type IS '产生事件的业务对象类型';
COMMENT ON COLUMN outbox_events.aggregate_id IS '产生事件的业务对象 ID；不设外键以保留消息审计';
COMMENT ON COLUMN outbox_events.payload IS '发布消息所需的参数快照';
COMMENT ON COLUMN outbox_events.status IS 'PENDING/PROCESSING/RETRY/PUBLISHED/FAILED';
COMMENT ON COLUMN outbox_events.attempt_count IS '已经尝试发布到 Redis 的次数';
COMMENT ON COLUMN outbox_events.max_attempts IS '允许发布的最大尝试次数';
COMMENT ON COLUMN outbox_events.available_at IS '下次允许发布的时间';
COMMENT ON COLUMN outbox_events.locked_at IS '发布器认领事件的时间';
COMMENT ON COLUMN outbox_events.locked_by IS '认领事件的发布器实例标识';
COMMENT ON COLUMN outbox_events.published_at IS '消息成功写入 Redis 的时间';
COMMENT ON COLUMN outbox_events.broker_task_id IS '发送给 Celery 的任务 ID';
COMMENT ON COLUMN outbox_events.last_error IS '最近一次发布失败的错误摘要';
COMMENT ON COLUMN outbox_events.created_at IS '事件创建时间';
COMMENT ON COLUMN outbox_events.updated_at IS '事件最后更新时间';

-- 知识文档索引生命周期：用于区分“只上传”与“已提交但卡住”，并支持补偿扫描。
ALTER TABLE knowledge_documents
    ADD COLUMN IF NOT EXISTS index_task_id VARCHAR(80),
    ADD COLUMN IF NOT EXISTS index_queued_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS index_started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS index_heartbeat_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS index_completed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS index_recovery_count INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS ix_knowledge_documents_index_recovery
    ON knowledge_documents(parse_status, index_queued_at, index_heartbeat_at)
    WHERE deleted_at IS NULL;

COMMENT ON COLUMN knowledge_documents.index_task_id IS '最近一次实际执行索引的 Celery 任务 ID';
COMMENT ON COLUMN knowledge_documents.index_queued_at IS '用户提交索引请求并登记发件箱事件的时间；为空表示只上传未提交';
COMMENT ON COLUMN knowledge_documents.index_started_at IS '最近一次索引 Worker 认领时间';
COMMENT ON COLUMN knowledge_documents.index_heartbeat_at IS '索引 Worker 最近心跳时间';
COMMENT ON COLUMN knowledge_documents.index_completed_at IS '最近一次索引成功或最终失败时间';
COMMENT ON COLUMN knowledge_documents.index_recovery_count IS '补偿扫描重新投递次数';

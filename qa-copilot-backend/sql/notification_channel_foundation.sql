BEGIN;

-- 设计文档要求通知配置统一使用 jsonb；USING 子句保留已有 JSON 数据。
ALTER TABLE notification_channels
    ALTER COLUMN config TYPE jsonb USING config::jsonb,
    ALTER COLUMN channel_type SET DEFAULT 'WEBHOOK',
    ALTER COLUMN config SET DEFAULT '{}'::jsonb,
    ALTER COLUMN encrypted_secret SET DEFAULT '',
    ALTER COLUMN enabled SET DEFAULT true,
    ALTER COLUMN importance_threshold SET DEFAULT 80,
    ALTER COLUMN breaking_only SET DEFAULT false;

-- PostgreSQL 没有 ADD CONSTRAINT IF NOT EXISTS，使用系统表保证脚本可重复执行。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_notification_channels_type'
    ) THEN
        ALTER TABLE notification_channels
            ADD CONSTRAINT chk_notification_channels_type
            CHECK (channel_type IN ('WEBHOOK', 'WECHAT_WORK_BOT', 'DINGTALK_BOT', 'SMTP'));
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_notification_channels_importance_threshold'
    ) THEN
        ALTER TABLE notification_channels
            ADD CONSTRAINT chk_notification_channels_importance_threshold
            CHECK (importance_threshold BETWEEN 0 AND 100);
    END IF;
END
$$;

COMMENT ON TABLE notification_channels IS '平台统一维护的自动化结果与系统告警通知渠道';
COMMENT ON COLUMN notification_channels.id IS '通知渠道主键';
COMMENT ON COLUMN notification_channels.name IS '通知渠道名称，供管理员和业务规则选择';
COMMENT ON COLUMN notification_channels.channel_type IS '渠道类型：WEBHOOK、WECHAT_WORK_BOT、DINGTALK_BOT 或 SMTP';
COMMENT ON COLUMN notification_channels.config IS '不含密钥的渠道配置，例如接收人、主题前缀和请求超时';
COMMENT ON COLUMN notification_channels.encrypted_secret IS '使用 DATA_ENCRYPTION_KEY 加密后的地址、令牌或邮箱密码';
COMMENT ON COLUMN notification_channels.enabled IS '是否允许业务任务使用该通知渠道';
COMMENT ON COLUMN notification_channels.importance_threshold IS '最低通知重要度，范围 0 到 100';
COMMENT ON COLUMN notification_channels.breaking_only IS '是否只发送阻断性失败或重要告警';
COMMENT ON COLUMN notification_channels.created_at IS '创建时间';
COMMENT ON COLUMN notification_channels.updated_at IS '更新时间';

-- 二级页面名需要使用 ai_ 前缀，才能匹配 Elegant Router 生成的组件映射。
UPDATE menus
SET route_name = 'ai_notification',
    component = 'view.ai_notification',
    updated_at = CURRENT_TIMESTAMP
WHERE route_name = 'notification_channel';

COMMIT;

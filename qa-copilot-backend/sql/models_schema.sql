BEGIN;

-- 本文件只创建 app/models 当前保留的 8 个实体及其必需的 2 张关联表。

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(64) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    is_active BOOLEAN NOT NULL,
    is_superuser BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username);

CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    code VARCHAR(64) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500) NOT NULL,
    enabled BOOLEAN NOT NULL,
    is_system BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_roles_code ON roles (code);

CREATE TABLE IF NOT EXISTS menus (
    id SERIAL PRIMARY KEY,
    parent_id INTEGER REFERENCES menus (id) ON DELETE CASCADE,
    route_name VARCHAR(120) NOT NULL,
    path VARCHAR(300) NOT NULL,
    component VARCHAR(200) NOT NULL,
    title VARCHAR(100) NOT NULL,
    icon VARCHAR(100) NOT NULL,
    "order" INTEGER NOT NULL,
    menu_type VARCHAR(20) NOT NULL,
    permission_code VARCHAR(120),
    enabled BOOLEAN NOT NULL,
    hidden BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_menus_parent_id ON menus (parent_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_menus_route_name ON menus (route_name);
CREATE UNIQUE INDEX IF NOT EXISTS ix_menus_permission_code ON menus (permission_code);

CREATE TABLE IF NOT EXISTS ai_providers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    provider_type VARCHAR(40) NOT NULL,
    base_url VARCHAR(500),
    encrypted_api_key TEXT NOT NULL,
    custom_headers JSON NOT NULL,
    timeout_seconds INTEGER NOT NULL,
    max_retries INTEGER NOT NULL,
    enabled BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS prompt_templates (
    id SERIAL PRIMARY KEY,
    code VARCHAR(80) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500) NOT NULL,
    system_prompt TEXT NOT NULL,
    user_prompt TEXT NOT NULL,
    enabled BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_prompt_templates_code ON prompt_templates (code);

CREATE TABLE IF NOT EXISTS notification_channels (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    channel_type VARCHAR(30) NOT NULL,
    config JSON NOT NULL,
    encrypted_secret TEXT NOT NULL,
    enabled BOOLEAN NOT NULL,
    importance_threshold INTEGER NOT NULL,
    breaking_only BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_notification_channels_channel_type
    ON notification_channels (channel_type);

-- User.roles 和 Role.users 是多对多关系，因此必须有用户角色关联表。
CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles (id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

-- Role.menus 和 Menu.roles 是多对多关系，因此必须有角色菜单关联表。
CREATE TABLE IF NOT EXISTS role_menus (
    role_id INTEGER NOT NULL REFERENCES roles (id) ON DELETE CASCADE,
    menu_id INTEGER NOT NULL REFERENCES menus (id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, menu_id)
);

CREATE TABLE IF NOT EXISTS ai_models (
    id SERIAL PRIMARY KEY,
    provider_id INTEGER NOT NULL REFERENCES ai_providers (id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    model_id VARCHAR(160) NOT NULL,
    reasoning_effort VARCHAR(20),
    context_window_tokens INTEGER NOT NULL DEFAULT 32768,
    max_output_tokens INTEGER NOT NULL,
    enabled BOOLEAN NOT NULL,
    is_default BOOLEAN NOT NULL,
    task_types JSON NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_provider_model UNIQUE (provider_id, model_id)
);

CREATE TABLE IF NOT EXISTS ai_usage_logs (
    id SERIAL PRIMARY KEY,
    provider_id INTEGER NOT NULL REFERENCES ai_providers (id),
    model_id INTEGER NOT NULL REFERENCES ai_models (id),
    task_type VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    total_tokens INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

COMMIT;

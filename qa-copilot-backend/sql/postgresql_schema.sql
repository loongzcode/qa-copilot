BEGIN;

CREATE TABLE sys_menu (
    id BIGSERIAL PRIMARY KEY,
    parent_id BIGINT REFERENCES sys_menu (id) ON DELETE RESTRICT,
    name VARCHAR(128) NOT NULL,
    route_name VARCHAR(128) NOT NULL UNIQUE,
    route_path VARCHAR(512) NOT NULL,
    component VARCHAR(255),
    menu_type INTEGER NOT NULL DEFAULT 2,
    icon VARCHAR(128),
    icon_type INTEGER,
    i18n_key VARCHAR(255),
    order_no INTEGER NOT NULL DEFAULT 0,
    href VARCHAR(2048),
    keep_alive BOOLEAN NOT NULL DEFAULT false,
    is_constant BOOLEAN NOT NULL DEFAULT false,
    hide_in_menu BOOLEAN NOT NULL DEFAULT false,
    active_menu VARCHAR(128),
    multi_tab BOOLEAN NOT NULL DEFAULT true,
    fixed_index_in_tab INTEGER,
    query_json JSONB,
    status INTEGER NOT NULL DEFAULT 1,
    created_by VARCHAR(64) NOT NULL DEFAULT 'system',
    updated_by VARCHAR(64) NOT NULL DEFAULT 'system',
    created_at TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    deleted_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_sys_menu_type CHECK (menu_type IN (1, 2)),
    CONSTRAINT chk_sys_menu_icon_type CHECK (icon_type IS NULL OR icon_type IN (1, 2)),
    CONSTRAINT chk_sys_menu_status CHECK (status IN (1, 2))
);

COMMENT ON TABLE sys_menu IS 'Soybean Admin 的动态路由和菜单';
CREATE INDEX ix_sys_menu_parent_order ON sys_menu (parent_id, order_no);
CREATE INDEX ix_sys_menu_status ON sys_menu (status);

CREATE TABLE sys_role (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    code VARCHAR(64) NOT NULL UNIQUE,
    description VARCHAR(500) NOT NULL DEFAULT '',
    status INTEGER NOT NULL DEFAULT 1,
    is_system BOOLEAN NOT NULL DEFAULT false,
    created_by VARCHAR(64) NOT NULL DEFAULT 'system',
    updated_by VARCHAR(64) NOT NULL DEFAULT 'system',
    created_at TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    deleted_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_sys_role_status CHECK (status IN (1, 2))
);

COMMENT ON TABLE sys_role IS 'RBAC 角色';
CREATE INDEX ix_sys_role_name ON sys_role (name);
CREATE INDEX ix_sys_role_status ON sys_role (status);

CREATE TABLE sys_user (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    nickname VARCHAR(64) NOT NULL DEFAULT '',
    gender INTEGER,
    phone VARCHAR(32) UNIQUE,
    email VARCHAR(255) UNIQUE,
    avatar_url VARCHAR(2048),
    status INTEGER NOT NULL DEFAULT 1,
    last_login_at TIMESTAMP WITH TIME ZONE,
    created_by VARCHAR(64) NOT NULL DEFAULT 'system',
    updated_by VARCHAR(64) NOT NULL DEFAULT 'system',
    created_at TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    deleted_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_sys_user_gender CHECK (gender IS NULL OR gender IN (1, 2)),
    CONSTRAINT chk_sys_user_status CHECK (status IN (1, 2))
);

COMMENT ON TABLE sys_user IS '兼容 Soybean 和 /api/users 接口的用户表';
CREATE INDEX ix_sys_user_status ON sys_user (status);
CREATE INDEX ix_sys_user_deleted_at ON sys_user (deleted_at);

CREATE TABLE sys_file (
    id BIGSERIAL PRIMARY KEY,
    uploader_id BIGINT REFERENCES sys_user (id) ON DELETE SET NULL,
    original_filename VARCHAR(255) NOT NULL,
    stored_filename VARCHAR(255) NOT NULL,
    storage_provider VARCHAR(32) NOT NULL DEFAULT 'LOCAL',
    bucket_name VARCHAR(128),
    object_key VARCHAR(512) NOT NULL,
    mime_type VARCHAR(128) NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 CHAR(64),
    url VARCHAR(2048) NOT NULL,
    status INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    deleted_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uk_sys_file_provider_object UNIQUE (storage_provider, object_key),
    CONSTRAINT chk_sys_file_status CHECK (status IN (1, 2)),
    CONSTRAINT chk_sys_file_size_bytes CHECK (size_bytes >= 0)
);

COMMENT ON TABLE sys_file IS '上传文件元数据，二进制内容保存在对象存储';
COMMENT ON COLUMN sys_file.storage_provider IS 'LOCAL 本地，MINIO，OSS，S3';
COMMENT ON COLUMN sys_file.status IS '1 可用，2 停用';
CREATE INDEX idx_sys_file_uploader_created ON sys_file (uploader_id, created_at);
CREATE INDEX idx_sys_file_sha256 ON sys_file (sha256);

CREATE TABLE sys_permission (
    id BIGSERIAL PRIMARY KEY,
    menu_id BIGINT REFERENCES sys_menu (id) ON DELETE SET NULL,
    name VARCHAR(128) NOT NULL,
    code VARCHAR(128) NOT NULL UNIQUE,
    permission_type VARCHAR(16) NOT NULL DEFAULT 'BUTTON',
    http_method VARCHAR(16),
    api_path VARCHAR(512),
    description VARCHAR(500) NOT NULL DEFAULT '',
    status INTEGER NOT NULL DEFAULT 1,
    created_by VARCHAR(64) NOT NULL DEFAULT 'system',
    updated_by VARCHAR(64) NOT NULL DEFAULT 'system',
    created_at TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    deleted_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_sys_permission_type CHECK (permission_type IN ('BUTTON', 'API', 'DATA')),
    CONSTRAINT chk_sys_permission_status CHECK (status IN (1, 2))
);

COMMENT ON TABLE sys_permission IS '按钮、接口和数据范围权限';
CREATE INDEX ix_sys_permission_menu ON sys_permission (menu_id);
CREATE INDEX ix_sys_permission_api ON sys_permission (http_method, api_path);

CREATE TABLE sys_refresh_token (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES sys_user (id) ON DELETE CASCADE,
    token_jti CHAR(36) NOT NULL UNIQUE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE,
    replaced_by_jti CHAR(36),
    client_ip VARCHAR(64),
    user_agent VARCHAR(512),
    created_at TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
);

COMMENT ON TABLE sys_refresh_token IS '刷新 Token 轮换和吊销记录';
COMMENT ON COLUMN sys_refresh_token.token_hash IS 'SHA-256 哈希，禁止保存原始刷新 Token';
CREATE INDEX idx_sys_refresh_token_user_expiry
    ON sys_refresh_token (user_id, expires_at);

CREATE TABLE sys_role_menu (
    role_id BIGINT NOT NULL REFERENCES sys_role (id) ON DELETE CASCADE,
    menu_id BIGINT NOT NULL REFERENCES sys_menu (id) ON DELETE CASCADE,
    created_at TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (role_id, menu_id)
);

COMMENT ON TABLE sys_role_menu IS '角色与菜单的关联';

CREATE TABLE sys_user_role (
    user_id BIGINT NOT NULL REFERENCES sys_user (id) ON DELETE CASCADE,
    role_id BIGINT NOT NULL REFERENCES sys_role (id) ON DELETE CASCADE,
    created_at TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (user_id, role_id)
);

COMMENT ON TABLE sys_user_role IS '用户与角色的关联';

CREATE TABLE sys_user_setting (
    user_id BIGINT PRIMARY KEY REFERENCES sys_user (id) ON DELETE CASCADE,
    settings_json JSONB NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT chk_sys_user_setting_version CHECK (version > 0)
);

COMMENT ON TABLE sys_user_setting IS '用户级项目和主题配置';

CREATE TABLE sys_role_permission (
    role_id BIGINT NOT NULL REFERENCES sys_role (id) ON DELETE CASCADE,
    permission_id BIGINT NOT NULL REFERENCES sys_permission (id) ON DELETE CASCADE,
    created_at TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (role_id, permission_id)
);

COMMENT ON TABLE sys_role_permission IS '角色与权限的关联';

CREATE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP(3);
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_sys_menu_updated_at
    BEFORE UPDATE ON sys_menu
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_sys_role_updated_at
    BEFORE UPDATE ON sys_role
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_sys_user_updated_at
    BEFORE UPDATE ON sys_user
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_sys_permission_updated_at
    BEFORE UPDATE ON sys_permission
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_sys_user_setting_updated_at
    BEFORE UPDATE ON sys_user_setting
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;

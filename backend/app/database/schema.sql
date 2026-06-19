-- Aureon PostgreSQL Schema
-- Created: 2026-06-19

-- 消息记录（L0）
CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    tokens INT DEFAULT 0,
    tool_name VARCHAR(128),
    tool_args TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    tenant_id VARCHAR(64) DEFAULT 'default'
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_tenant ON messages(tenant_id);

-- 原子事实（L1）
CREATE TABLE IF NOT EXISTS atoms (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    subject VARCHAR(256) NOT NULL,
    predicate VARCHAR(256) NOT NULL,
    object TEXT NOT NULL,
    message_id BIGINT,
    confidence REAL DEFAULT 0.5,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    tenant_id VARCHAR(64) DEFAULT 'default'
);
CREATE INDEX IF NOT EXISTS idx_atoms_session ON atoms(session_id);
CREATE INDEX IF NOT EXISTS idx_atoms_tenant ON atoms(tenant_id);

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(128),
    password_hash VARCHAR(256) NOT NULL,
    role VARCHAR(16) DEFAULT 'viewer',
    tenant_id VARCHAR(64) DEFAULT 'default',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- 审计日志
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(64),
    action VARCHAR(64) NOT NULL,
    resource VARCHAR(128),
    detail TEXT,
    ip_address VARCHAR(45),
    tenant_id VARCHAR(64) DEFAULT 'default',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_logs(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id, created_at);

-- Feature flags
CREATE TABLE IF NOT EXISTS feature_flags (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(128) UNIQUE NOT NULL,
    description TEXT,
    enabled BOOLEAN DEFAULT FALSE,
    rollout_percentage INT DEFAULT 0,
    tenant_id VARCHAR(64) DEFAULT 'default',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 知识库文档元数据
CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(512) NOT NULL,
    source VARCHAR(512),
    file_type VARCHAR(16),
    chunks_count INT DEFAULT 0,
    tenant_id VARCHAR(64) DEFAULT 'default',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_documents_tenant ON documents(tenant_id);

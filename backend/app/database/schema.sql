-- Aureon PostgreSQL Schema
-- Created: 2026-06-19
-- Updated: 2026-07-05 — Consolidated tables, PostgreSQL-only (SQLite removed).
-- Note: conversations + atoms + query_traces tables are managed by memory/pg.py (SQLAlchemy metadata).

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    status TEXT NOT NULL DEFAULT 'active',
    tenant_id TEXT NOT NULL DEFAULT 'default',
    workspace_ids TEXT DEFAULT '[]',
    last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- 审计日志
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    user_id TEXT NOT NULL DEFAULT 'anonymous',
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL DEFAULT '',
    resource_id TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    ip_address TEXT NOT NULL DEFAULT '',
    request_id TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);

-- SSO 提供商
CREATE TABLE IF NOT EXISTS sso_providers (
    id BIGSERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    provider_type TEXT NOT NULL,
    client_id TEXT,
    client_secret TEXT,
    metadata_url TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- PII 检测记录
CREATE TABLE IF NOT EXISTS pii_detections (
    id BIGSERIAL PRIMARY KEY,
    document_id TEXT,
    pii_type TEXT NOT NULL,
    value_hash TEXT NOT NULL,
    original_length INTEGER,
    masked_value TEXT,
    action_taken TEXT DEFAULT 'mask',
    detected_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pii_detections_document ON pii_detections(document_id);

-- Feature flags
CREATE TABLE IF NOT EXISTS feature_flags (
    id BIGSERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    percentage INTEGER NOT NULL DEFAULT 0,
    conditions TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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

-- 分析事件持久化表（跨部署保留）
CREATE TABLE IF NOT EXISTS analytics_events (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) DEFAULT 'default',
    event_type VARCHAR(32) NOT NULL DEFAULT 'query',
    query_text TEXT,
    sources_count INT DEFAULT 0,
    latency_ms REAL DEFAULT 0,
    ttft_ms REAL DEFAULT 0,
    tpot_ms REAL DEFAULT 0,
    tokens_in INT DEFAULT 0,
    tokens_out INT DEFAULT 0,
    model VARCHAR(128),
    intent VARCHAR(64) DEFAULT 'general_qa',
    cache_hit BOOLEAN DEFAULT FALSE,
    error BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_analytics_tenant_time ON analytics_events(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_type ON analytics_events(event_type, created_at DESC);

-- 日聚合缓存
CREATE TABLE IF NOT EXISTS analytics_daily (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) DEFAULT 'default',
    date DATE NOT NULL,
    total_queries INT DEFAULT 0,
    errors INT DEFAULT 0,
    cache_hits INT DEFAULT 0,
    tokens_in BIGINT DEFAULT 0,
    tokens_out BIGINT DEFAULT 0,
    avg_latency_ms REAL DEFAULT 0,
    p95_latency_ms REAL DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, date)
);
CREATE INDEX IF NOT EXISTS idx_analytics_daily_tenant ON analytics_daily(tenant_id, date DESC);

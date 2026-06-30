-- Aureon PostgreSQL Schema
-- Created: 2026-06-19
-- Note: conversations + atoms tables are managed by memory/pg.py (SQLAlchemy metadata).

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

-- 分析事件持久化表（跨部署保留）
-- 每次 RAG 查询记录一条，用于 Dashboard / Analytics 页面在 Redis 清空后恢复数据
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

-- 日聚合缓存（加速 Dashboard 图表查询）
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

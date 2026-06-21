-- 001_initial: Base schema for users and audit_logs
-- This is idempotent ¡ª uses IF NOT EXISTS

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    password_hash VARCHAR(255),
    role VARCHAR(50) DEFAULT 'user',
    is_active BOOLEAN DEFAULT TRUE,
    tenant_id VARCHAR(100) DEFAULT 'default',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100),
    action VARCHAR(100) NOT NULL,
    resource VARCHAR(255),
    detail TEXT,
    ip_address VARCHAR(50),
    tenant_id VARCHAR(100) DEFAULT 'default',
    created_at TIMESTAMP DEFAULT NOW()
);
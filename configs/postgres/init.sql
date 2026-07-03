CREATE DATABASE agent_audit;
GRANT ALL PRIVILEGES ON DATABASE agent_audit TO agentos;

-- 预留：创建未来联邦记忆温层需要的元数据表（先空着）
CREATE TABLE IF NOT EXISTS memory_meta (
    id SERIAL PRIMARY KEY,
    memory_type TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
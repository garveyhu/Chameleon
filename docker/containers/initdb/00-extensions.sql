-- Chameleon Postgres 首启动扩展
-- pgvector：向量列；pg_trgm：模糊检索

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

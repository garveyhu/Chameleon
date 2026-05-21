# ADR 0011：知识库选 pgvector 而非独立向量数据库

- **Status**: Accepted
- **Date**: 2026-04

## 背景

知识库需要向量检索。候选：
1. **pgvector**：PG 扩展，与业务 DB 共用
2. **Milvus / Weaviate / Qdrant**：专用向量 DB

## 决策

**pgvector + HNSW 索引 + pg_trgm 模糊** —— v0.1 不引入独立向量 DB。

## 理由

| 维度 | pgvector | Milvus / Qdrant |
|---|---|---|
| 部署复杂度 | 0（PG 扩展） | 多一套服务 + 数据备份 |
| 与业务 DB 事务一致 | 同一事务 | 跨服务，最终一致 |
| 性能 (百万级) | HNSW 50ms 内 | 更优（千万级见效） |
| 运维成熟度 | PG 团队即可 | 需要专门人 |
| 与 SA 集成 | 官方 dialect | 自封装 |

Chameleon 早期场景：单租户知识库 chunks 量级 10万-100万。pgvector 完全够用。当突破百万时再考虑迁移。

## 实现要点

- `chunks.embedding vector(1536)` 列
- HNSW 索引：`CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)`
- 全文：`pg_trgm` GIN 索引 + `ILIKE` 模糊
- 召回：向量 top-k + 全文 top-k → Reciprocal Rank Fusion（RRF）合并

## 后果

- chunks 表如果膨胀很大，HNSW 索引重建会成本高 → 监控 chunks 增长率
- 升级到独立向量 DB 是后续 ADR-XXX 的事，写好抽象层（`VectorStore` interface）让切换平滑
- pgvector 版本需匹配 PG 主版本（compose 用 `pgvector/pgvector:pg16`）

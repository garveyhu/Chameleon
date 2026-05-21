# ADR 0007：LLMFactory 启动期 async load + 业务热路径同步读

- **Status**: Accepted
- **Date**: 2026-04

## 背景

`LLMFactory.create("qwen-plus")` 在业务 invoke 链路上被频繁调用。如果每次都查 DB → 解密 api_key → 构造 OpenAI client，会：

1. 业务 latency 增加（DB round trip + 解密 + client 构造）
2. async 染色到所有调用方
3. DB 连接池压力

## 决策

**启动期 async load 到 in-memory dict cache，业务热路径同步读 dict（O(1)）**。

```python
# startup
await reload_llm_cache()   # async query DB, fill _CACHE: dict[str, BaseLLM]

# hot path
client = LLMFactory.create("qwen-plus")  # 同步从 _CACHE 拿
```

admin 改 model 配置后调 `reload_llm_cache()` 重 load 全量；不做 lazy / per-row 失效（实现复杂、容易出竞态）。

## 理由

| 维度 | lazy load | startup load |
|---|---|---|
| 业务 latency | 首次 DB query + 解密 | 0（dict 读） |
| async 染色 | 业务路径 async | 业务路径 sync 即可 |
| 一致性 | 并发安全难做 | 全量 reload 简单 |
| 失败处理 | 业务路径要兜底 | 启动 fail-fast |

模型数量是 O(几十)，全量 reload 0.1s 以内，完全可接受。

## 后果

- admin 改 model 不刷新 cache = 改了不生效（admin API 改完必须显式 `await reload_llm_cache()`）
- 多实例：每个实例独立 cache，admin 在 instance-A 改后只刷 A 的 cache。
  → v0.2 Roadmap：Redis pub/sub 广播 invalidate 事件让所有实例 reload

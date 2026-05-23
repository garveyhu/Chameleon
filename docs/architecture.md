# Chameleon 架构（v1.0）

## 一、分层

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (React 19 + Vite + Tailwind v4)               │
│  /system/{dashboard, agents, kbs, graphs, playground,   │
│           call_logs, conversations, traces, datasets,   │
│           marketplace, ...}                              │
└──────────────┬──────────────────────────────────────────┘
               │ HTTP (proxy via vite dev server)
               │
┌──────────────▼──────────────────────────────────────────┐
│  Backend FastAPI (chameleon-app)                         │
│  ├─ chameleon-api/    业务 HTTP (/v1/conversations,     │
│  │                    /v1/agents, /v1/otel/v1/traces)   │
│  └─ chameleon-system/ admin HTTP (/v1/admin/*)          │
└──────────────┬──────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────┐
│  chameleon-core (基础设施 + 算子)                         │
│  ├─ models/      ORM (SQLAlchemy 2 async)              │
│  ├─ infra/       DB / Redis / JWT / 加密 / auth         │
│  ├─ retrieval/   hybrid / reranker / vlm_caption        │
│  ├─ eval/        RAGAS 4 算子                           │
│  ├─ sandbox/     docker / mock runtime                  │
│  ├─ graph/       Graph executor + nodes                 │
│  ├─ agent/       A2A 协议 + AgentRunner                 │
│  ├─ observe/     observation context manager            │
│  ├─ plugins/     hot loader + manifest signing          │
│  └─ tools/       Tool 注册表 + builtin code-runner     │
└──────────────┬──────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────┐
│  chameleon-providers/                                     │
│  base / local / dify / fastgpt / openai-compat / ...    │
└──────────────┬──────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────┐
│  PostgreSQL 16 + pgvector + Redis + MinIO + (docker)    │
└─────────────────────────────────────────────────────────┘
```

## 二、关键数据流

### 普通 invoke

```
client → /v1/agents/{key}/invoke
   → chameleon-api/agent/service.invoke()
      ① AGENTS.get(key) → AgentDef
      ② conv_service.create / get + history load
      ③ append user msg
      ④ provider.invoke(InvokeContext)  ← 内部 observe context manager
      ⑤ append assistant msg + touch conv
      ⑥ record_call (cost_usd 自动算 + workspace quota 累加)
```

### Graph 执行

```
client → /v1/admin/graphs/{id}/run
   → graph_runner.run_graph()
      ① GraphSpec 校验
      ② GraphExecutor 拓扑序遍历
      ③ 每节点 await execute(NodeContext, input)
      ④ ToolNode → sandbox runtime / KB / LLM / agent_debate
      ⑤ 写 graph_node_runs + 串到 call_logs trace
```

### OTLP 摄入

```
SDK client → POST /v1/otel/v1/traces
   → chameleon-api/otel/api.export_traces()
      ① current_app dep 鉴权
      ② 每 span → converter.convert_and_persist_span()
         - 推 observation_type（attributes.gen_ai.* / openinference / scope）
         - 抽 prompt/completion/total tokens
         - traceId + spanId → request_id / parent_id
      ③ record_call 落 call_logs
```

### RAG 检索

```
client → /v1/admin/kbs/{id}/search （或 KbNode）
   → document_service.search_chunks()
      mode=vector：纯向量
      mode=keyword：纯 BM25
      mode=hybrid：HybridPipeline 6 步
         ① vector_recall(top_k * 2)
         ② keyword_recall(top_k * 2)
         ③ dedupe by chunk_id
         ④ fuse_rrf
         ⑤ metadata_filter（quarantined / collection / kind / min_score）
         ⑥ optional reranker hook
      → 返 top_k chunks
```

## 三、关键 schema 关系

```
workspaces ←─ users / agents / kbs / graphs / datasets / eval_jobs ...
                   ↑
              workspace_quotas（月度 reset cron）

apps ←─ api_keys ←─ call_logs ← record_call (trace 嵌套 by parent_id)
                                ↑ cost_usd 用 model_pricing 算

knowledge_bases ←─ kb_collections (4 类) ←─ documents ←─ chunks
                                                          ↑ kind text/image
                                                          ↑ quarantined（半软删）

graphs (draft spec) ──publish──→ published_spec (freeze) + published_version++

datasets ←─ dataset_items (PII 脱敏 mask/drop/keep)
                  ↑
              dataset_runs ←─ dataset_run_items (eval_scores by EvalTemplate)

conversations ←─ messages (parent_message_id 树形分支)

audit_logs (11 维: actor / workspace / session / action / before / after / ip / ...)
```

## 四、红线一览

| 阶段 | 红线 |
|---|---|
| P17 | DB-driven 配置不写代码常量；admin 改即生效 |
| P18 | GraphSpec 必须可序列化；executor 不持可变全局状态 |
| P19 | Eval cron 不阻塞业务；plugin 热加载 5s 超时；workspace_id 全 NULLABLE |
| P20 | Sandbox 不在主进程跑用户代码；manifest 必须验签；A2A 必须传 trace_id；KbCollection 类型不可改 |
| P21 | Dataset 采样必 PII 脱敏；RAGAS 算子注册表只读；KB 一致性不在线删；regenerate 不破坏老分支；EvalTemplate 改动有版本 |
| P22 | OTLP 鉴权；SDK v1.0 后 deprecation policy；Workflow published 不可改；VLM 走 URL；应用市场 install 经审核；Cost 可重放 |

详见各阶段 detail plan：`docs/plans/`

# Chameleon 架构

Chameleon = 开源 LLMOps 一站式平台：多源 AI 聚合 + 工作流编排 + RAG 知识库 + Trace/Eval 可观测 + 多 agent 协同 + 可嵌入 SDK。单租户部署。

## 一、分层

后端是 10 个 uv-workspace 包，依赖严格单向，由 import-linter 强制（两条契约常驻 GREEN）：

```
core ← data ← integrations ← engine ← (providers / api / system / app / agents / agentkit)
```

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (React 19 + Vite + Tailwind v4 + Radix)        │
│  4 导航域：工作台 / 知识库 / 观测 / 设置                  │
│  src/{core(共享), system/<module>(自包含), api-docs}      │
└──────────────┬──────────────────────────────────────────┘
               │ HTTP (vite dev proxy /v1 → 127.0.0.1:7009)
               │
┌──────────────▼──────────────────────────────────────────┐
│  chameleon-app  薄 FastAPI 启动器                         │
│  装配 + lifespan + 中间件 + DI 注入                       │
│  ├─ chameleon-api/    对外 AI 服务 API + OTLP 摄入        │
│  │     /v1/{sessions,kb,embed,files,tasks,otel,auth}     │
│  │     + /v1/invoke + OpenAI 兼容 /v1/chat/completions    │
│  └─ chameleon-system/ 内部 admin 管理 API (/v1/admin/*)   │
└──────────────┬──────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────┐
│  chameleon-providers  provider 抽象 + 实现（子 workspace）│
│  base(协议/types/registry) / local(进程内 BaseAgent)      │
│  / dify / fastgpt / graph(工作流即 agent)                 │
└──────────────┬──────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────┐
│  chameleon-engine  编排                                   │
│  graph(工作流引擎 + nodes) / retrieval(hybrid 检索管线)   │
│  / eval / agent(a2a) / jobs                               │
└──────────────┬──────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────┐
│  chameleon-integrations  厂商/外部实现                    │
│  llms(LLM 工厂) / vector(pgvector/chroma) / observe(落库   │
│  call_logs) / bridges(langchain 桥) / knowledge / tools   │
│  / plugins(registry)                                     │
└──────────────┬──────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────┐
│  chameleon-data  ORM(SQLAlchemy 2 async) + infra + utils  │
│  models/ · infra/{db,redis,object_store,jwt,auth,logger}  │
│  · utils/{crypto,...} · 配置加载                          │
└──────────────┬──────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────┐
│  chameleon-core  纯协议 + 数据结构 + observe 切面          │
│  pydantic-only（禁 sqlalchemy / langchain）              │
│  api / sandbox(docker/mock runtime) / observe(ContextVar) │
└──────────────┬──────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────┐
│  PostgreSQL 16 + pgvector + Redis + MinIO + (docker)     │
└─────────────────────────────────────────────────────────┘
```

旁支两包（不在主分层链上，依赖 providers/engine 侧）：

- **chameleon-agents**：业务级本地 agent（含 `examples/`）。
- **chameleon-agentkit**：进程内 agent SDK——`@agent` + `ctx` 隐式拿模型 / KB / trace，多具名模型槽，配置 Schema 自动生成表单，entry-points 发现。

## 二、关键数据流

### 普通 invoke

```
client → POST /v1/invoke   （app-key 隐含 agent，或 global-key 显式传 agent_key）
   → chameleon-api/agent/service.invoke()
      ① 解析 agent_key → AgentDef（AGENTS.get）
      ② 历史装载：input=str → 取 / 建 ChatSession；input=list → 客户端自管
      ③ append user message
      ④ 装 InvokeContext，调 provider.invoke()  ← observe 切面自动埋点
      ⑤ append assistant message
      ⑥ touch 会话（last_message_at / title / provider_conv_id）
      ⑦ observe sink 落 call_logs（cost_usd 由 model_pricing 自动算）
```

### Graph 执行

```
client → POST /v1/admin/graphs/{id}/run
   → engine/graph 引擎
      ① GraphSpec 校验（可序列化；executor 不持可变全局状态）
      ② 拓扑序遍历执行
      ③ 每节点 await execute(NodeContext, input)
      ④ 节点类型：LLM / KB / Tool / HTTP / Code(沙箱) / Template /
         意图分类(Classifier) / 聚合 / Answer / If-Else /
         Iteration / Parallel / AgentDebate / HumanInput
      ⑤ 每节点发 span 进 trace 树（observation_type + parent_id）
      ⑥ graph_runs 只留运行头 + human-input resume 锚
```

graph 也可作为 `source='graph'` 的 provider 对外暴露（工作流即 agent）。

### OTLP 摄入

```
SDK client → POST /v1/otel/v1/traces
   → chameleon-api/otel/api.export_traces()
      ① API key 鉴权
      ② 每 span → converter.convert_and_persist_span()
         - 推 observation_type（attributes.gen_ai.* / openinference / scope）
         - 抽 prompt / completion / total tokens
         - traceId + spanId → request_id / parent_id
      ③ 落 call_logs
```

### RAG 检索

```
client → POST /v1/admin/kbs/{id}/search （或 graph 的 KbNode）
   → retrieval 管线
      mode=vector：纯向量
      mode=keyword：纯 BM25
      mode=hybrid：HybridPipeline
         ① vector_recall(top_k * 2)
         ② keyword_recall(top_k * 2)
         ③ dedupe by chunk_id
         ④ fuse_rrf
         ⑤ metadata_filter（quarantined / collection / kind / 元数据字段 / min_score）
         ⑥ optional reranker hook
      → 返 top_k chunks
```

会话文件走 ephemeral RAG：小文件全文注入、大文件切块向量入临时 KB。

## 三、关键 schema 关系

ORM 模型在 `backend/chameleon-data/src/chameleon/data/models/`。

```
api_keys（scope_type = global / app / kb；前缀 chm_ / app- / kbs-；
          scope_ref 指向域内目标；plain_key 明文留存）
   └─ call_logs ← observe sink（嵌套 observation by parent_id）
                  ↑ cost_usd 用 model_pricing 算
                  ↑ session_id / end_user_id 冗余，便于按会话 / 终端用户聚合

knowledge_bases ←─ kb_collections (generic/faq/wiki/api，各自 chunker)
                        ←─ documents ←─ chunks
                                          ↑ kind text/image（VLM caption）
                                          ↑ quarantined（半软删，一致性扫描标记）
            + kb_metadata_fields（元数据字段，支持按字段过滤召回）

graphs (draft spec) ──publish──→ published_spec (freeze) + published_version++
   └─ graph_runs（运行头 + human_input resume 锚；节点明细不单独建表，
                  统一落 call_logs span/generation 行）

sessions (ChatSession + end_user_id 身份层) ←─ messages
                                                 ↑ parent_message_id 树形分支
   + session_files ←─ session_file_chunks（ephemeral RAG）

datasets ←─ dataset_items（PII 脱敏 mask/drop/keep；来源 call_log.request_id）
                  ↑
              dataset 评测 ←─ eval_jobs / eval_templates（版本化）

scores（call_log trace 根或子 observation 上的评分事件，指向 request_id）

audit_logs（actor / action / resource_type / resource_id / before / after
            / ip / user_agent / request_id / session_id / created_at）
```

> 概念变更（大重构后）：Workspace / 多租户配额、Channels / Abilities 渠道矩阵、
> Apps 容器、Conversations 均已删除。模型聚合 / 路由改走外部 oneapi；
> Conversations 更名 Sessions（带 end_user_id 身份层，支撑嵌入式 / 多用户）；
> API 密钥归属重锚到 app / agent / kb 作用域。

## 四、可观测（LangSmith 化）

- `call_logs` 是唯一 trace 真相源。
- trace 树 = 嵌套 observation（span + generation），由 `parent_id` 自引组织；NULL = trace root。
- graph 节点发 span 进同一棵 trace 树；根行做 rollup（汇总 model / token / cost）。
- 前端可观测域拆 **Trace** · **Session** 两 tab。

## 五、工具链 / SDK / 部署

| 维度 | 工具 |
|---|---|
| 后端 | uv（workspace）· ruff · pytest · **import-linter（分层护栏，2 契约 GREEN）** |
| 前端 | yarn + vite · eslint · tsc（strict）· TanStack Query + Zustand + ReactFlow |
| SDK | Python `chameleon-sdk`（httpx sync+async，`@trace` / `patch_openai` / `patch_all`）· TypeScript `@chameleon/sdk`（OTLP HTTP） |
| 部署 | Docker + Compose，多阶段镜像，`docker/` 三区（images / containers / scripts）；后端默认 7009，前端 dev 6006 |

## 六、红线一览

| 域 | 红线 |
|---|---|
| 分层 | import-linter 单向依赖不可破；core 禁 sqlalchemy / langchain；业务包不互相依赖 |
| 配置 | DB-driven 配置不写代码常量；admin 改即生效 |
| 工作流 | GraphSpec 必须可序列化；executor 不持可变全局状态；published 快照不可改 |
| 沙箱 | 用户代码不在主进程跑，走 sandbox（docker / mock runtime） |
| 插件 | manifest 必须验签；热加载 5s 超时 |
| 检索 | KbCollection 类型一经写入不可改；KB 一致性扫描不在线删（半软删 quarantined） |
| 数据 | Dataset 采样必 PII 脱敏；regenerate 不破坏老分支；EvalTemplate 改动有版本 |
| 可观测 | call_logs 是唯一 trace 真相源；A2A / graph 节点必须传 trace_id；Cost 可重放 |
| 接入 | OTLP 鉴权；SDK 对外 public API 走 deprecation policy；VLM 走 URL |

详见各阶段 detail plan：`docs/plans/`

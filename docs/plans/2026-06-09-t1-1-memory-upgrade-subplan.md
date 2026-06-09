# T1-1 memory 升级 · 细化子方案（待评审）

> 父计划 [[docs/plans/2026-06-09-agentkit-capability-enhancements.md]] T1-1。
> 本文是动手前的细化设计，**过目后再实现**。三子片 M1/M2/M3 各自可独立验证 + 独立 commit。

## 0. 现状实地核查（已读码确认）

| 件 | 位置 | 现状 |
|---|---|---|
| ctx.memory 表面 | `agentkit/_runtime.py` `MemoryHandle` / `_MemoryProxy` | 仅 `get/set/all`（KV） |
| 生产 transport | `providers/local/agentkit_runner.py::InProcessTransport` | `memory_get/set/all` 直打 `AgentMemory` 表；`kb_search` 走 `providers.base.retrieval_bridge.get_retrieve_fn()` IoC 桥 |
| 持久层 | `data/models/agent_memory.py::AgentMemory` | `(agent_key, scope_ref, mkey, value JSON)` uq(agent_key,scope_ref,mkey)；scope_ref = end_user_id 优先 / session_id 退化 |
| 检索栈 | `engine/retrieval/pipeline.py` | **KB-bound**（绑 `Chunk.kb_id`）→ 不能整体复用；可复用积木：`integrations.embedding.get_embedding_client` + `engine.retrieval.hybrid.HybridPipeline` + `engine.retrieval.rerankers.build_reranker` |
| KB 桥范式 | `providers/base/retrieval_bridge.py` (`set_retrieve_fn`/`get_retrieve_fn`) | engine 启动 `wire_retrieval_bridge()` 注入 → agentkit/providers **不反依赖 engine** |
| 任务范式 | `aikit/base.py::LLMRunner` + `aikit/tasks/retrieval/expander.py` | 纯任务 = build_prompt + LLMRunner.run_text + parse；aikit 不依赖 engine |

**分层铁律落点**：vector 召回的 embedding/hybrid/rerank 实现放 engine，经**新 IoC 桥** `providers.base.memory_vector_bridge` 注入；agentkit 只加表面，providers/local 只调桥 + 自己的表 SQL（它已直连 `data.models`）。**agentkit / providers 不反依赖 engine**，与 KB 路径同构。

---

## M1 · 语义召回（semantic recall）—— 首推，自包含

### 表面（agentkit）
- `MemoryHandle.search(query, *, top_k=5, min_score=0.0) -> list[MemoryHit]`
  - `MemoryHit`（新 dataclass，放 `_spec.py`）：`{key, value, text, score}`。
- `_MemoryProxy.search` → `RuntimeTransport.memory_search`（新 abstract）。
- 全 transport 补实现：InProcess（生产）/ Standalone / HttpDev / Sandbox / Fake(testing)。

### 存储（新表，新迁移）
新表 `agent_memory_vector`（pgvector），与 AgentMemory 旁路并存（**非破坏**，KV 仍是真相）：
```
id BIGINT PK
agent_key   VARCHAR(128)  index
scope_ref   VARCHAR(128)            -- 同 AgentMemory：end_user_id / session_id
mkey        VARCHAR(128)
text        TEXT                    -- value 的文本投影（embed 输入 + 召回回显）
embedding   VECTOR(1536)            -- 跟随默认 embedding 模型维度
updated_at  TIMESTAMPTZ
UNIQUE(agent_key, scope_ref, mkey)
```
迁移走 Alembic（参照既有 pgvector 列写法）。**不复用 KB Chunk 表**——避免把 memory 耦合进 KB schema / 拿 scope 假装 kb_id（[[api-key-scope-model]] scope 纪律）。

### 旁路索引（写路径）
`InProcessTransport.memory_set(k, v)` 现状只 upsert AgentMemory。改为：KV upsert 后，把 `v` 文本投影（str→原样；dict/list→`json.dumps` 或取约定文本字段）经桥 `memory_vector_bridge.index_fn(agent_key, scope_ref, mkey, text)` embed + upsert 到 `agent_memory_vector`。**删时同删**（v=None / 约定删除）。索引失败不阻塞 set（warn + 降级，KV 仍成功）。

### 召回（读路径）
`InProcessTransport.memory_search(query, top_k, min_score)` → 桥 `memory_vector_bridge.search_fn(agent_key, scope_ref, query, top_k, min_score)`：
- engine 侧实现：`get_embedding_client(model).embed([query])` → `agent_memory_vector` 按 `(agent_key, scope_ref)` 过滤 + cosine 召回 → **可选 rerank**（`build_reranker`，默认关）→ top_k/min_score。
- **scope 隔离硬约束**：WHERE 必带 `agent_key == self._agent_key AND scope_ref == self._scope_ref`，与 KV 同维度，绝不串号。

### 范围决策（待定 → 见末尾问题）
- v1 **vector + 可选 rerank**（memory 条目短，BM25 边际低）；hybrid 全量 BM25 over memory 延后。
- 召回是否自动注入 system（像 working memory）？v1 **不自动**，作者显式 `ctx.memory.search` 拿了自己拼 context（与 ctx.kb.search 一致，控制权在作者）。

### 验收
真库往返：set 多条跨"会话"（同 end_user 不同 session）→ search 语义命中（非字面匹配）；scope 隔离测试（A 的 end_user 搜不到 B 的）；7009 真跑一个 demo agent。

---

## M2 · working memory —— 结构化槽自动注入

### 声明（agentkit）
`@agent(working_memory=MySchema)`（`MySchema: type[BaseModel]`）。`_spec.py` AgentManifest 加 `working_memory: type[BaseModel] | None`；`_decorator.py` 透传。

### 持久 + 注入
- 落 AgentMemory 一个**保留 key** `__chm_working__`（已被 `_MemoryProxy.all()` 的 `__chm_*__` 过滤，作者 KV 视图不可见）。
- 运行时（`agentkit_runner.run_agentkit`）调 handle **前**：若声明了 working schema → `memory_get(__chm_working__)` 取值 → 渲染成 system 注入块（"已知用户偏好/事实：…"）→ 挂到 `AgentRun._working_memory_text`。
- `_build_messages` 若 `self._working_memory_text` 非空 → 注入 system 头部（在作者 system 之后、history 之前）。
- 增量改：`ctx.memory.update_working(**fields)`（`_MemoryProxy` 新方法）→ 读旧槽 + merge + 写回 `__chm_working__` + 触发 M1 旁路索引（让 working 事实也可被语义召回）。`ctx.memory.get_working()` 取当前槽。

### 验收
声明 schema 的 agent，第二轮对话能在 system 看到上一轮 `update_working` 写的事实；保留 key 不污染 `.all()`。

---

## M3 · observational 压缩 —— 最大/最险，建议 M1+M2 落地后单独片

### 任务（aikit，纯任务）
- 新 `aikit/tasks/memory/observer.py`：`observe(history_text) -> list[str]`（抽稠密观察），`LLMRunner.run_text` + parse。
- 新 `aikit/tasks/memory/reflector.py`：`reflect(old_observations, new_observations) -> list[str]`（合并去重）。
- 二者纯 prompt+parse，照 `tasks/retrieval/expander.py`。aikit 不依赖 engine/agentkit。

### 触发 + 落地（非破坏）
- 触发：一次 run 结束后，若 history 长度 / memory 条目数超阈值 → fire-and-forget asyncio 任务（参照站内 followups 异步范式）跑 Observer→Reflector。
- 落地：把压缩观察写 `__chm_observations__`（保留 key）+ 旁路 M1 索引；**保留原始条目不删**（可保留原始 + 加压缩视图）。长对话 search 命中稠密观察，上下文窗口稳定。

### 验收
长对话/大记忆触发压缩；压缩后关键事实仍可召回；主调用不被阻塞（异步）。**风险**：压缩别丢关键事实 → 非破坏式（留原始）+ Reflector 合并而非覆盖。

---

## 实施顺序 & commit 粒度
1. **M1**（表面 + 新表迁移 + 桥 + 旁路索引 + 召回 + 真库往返测试 + 7009 demo）→ commit。
2. **M2**（声明 + 注入 + update_working + 测试）→ commit。
3. **M3**（observer/reflector 任务 + 触发 + 非破坏落地 + 测试）→ commit（或拆 observer / 触发两 commit）。

每片：ruff + boot + lint-imports（验 agentkit/providers 不反依赖 engine 契约仍 GREEN）；M1/M2 无前端改动（纯 SDK 能力，运营面记忆查看 UI 另议）。

## 已评审决策（2026-06-09 锁定）
1. **存储**：✅ 新 `agent_memory_vector` 表。
2. **召回深度**：✅ **full hybrid**（vector + BM25 over memory text + 可选 rerank）。
   → `agent_memory_vector` 加 `text_search`（jieba 切词）+ `content_tsv`(GENERATED tsvector)+GIN，
     engine 侧召回镜像 `pipeline.py` 的 `_build_vector_recall`+`_build_keyword_recall`+`HybridPipeline`。
3. **M3 排期**：✅ 本轮 M1+M2+M3 三片全做完（各自独立 commit）。

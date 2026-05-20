# Chameleon v1 验收报告

**日期**：2026-05-20
**版本**：v0.1.0
**测试通过**：116 / 116  ·  **lint 通过**：100%  ·  **migrations**：0002 (head)

依据：设计文档 S6.3 三轴验收清单（功能 / 架构 / 规约）。

---

## 功能轴

| # | 验收项 | 状态 | 证据 |
|---|---|---|---|
| 1 | FastAPI app 可启动 | ✅ | `uvicorn chameleon.app.main:app` 启动 + 日志显示 "FastAPI app created" |
| 2 | `/health` 返 `{"ok": true}` | ✅ | `curl /health → {"ok":true}` |
| 3 | `/ready` 返 db + pgvector OK | ✅ | `curl /ready → {"data":{"db":true,"pgvector":true}}` |
| 4 | CLI `chameleon init-admin` 落第一个 admin key | ✅ | T3.1 实测；当前 DB 已有 admin-cli 记录 |
| 5 | admin key 通过 `POST /v1/admin/api-keys` 发普通 key | ✅ | `test_admin_create_app_key` |
| 6 | ≥ 1 个本地 LangGraph agent 可调（echo） | ✅ | `test_echo_invoke_non_stream` + `test_echo_invoke_stream` |
| 7 | ≥ 1 个外部 DIFY agent 接入并可调 | ✅ | `test_dify_invoke_non_stream` + `test_dify_invoke_stream` |
| 8 | ≥ 1 个外部 FastGPT agent 接入并可调 | ✅ | `test_fastgpt_invoke_non_stream` + `test_fastgpt_invoke_stream` |
| 9 | `POST /v1/agents/{key}/invoke` 非流模式通 | ✅ | `test_invoke_non_stream_str_input` |
| 10 | 同接口 SSE 模式通 | ✅ | `test_stream_all_event_types` + `test_echo_invoke_stream` |
| 11 | `session_id` 自动签发 + 多轮历史回放 | ✅ | `test_invoke_multi_turn_history_replay` + `test_stream_multi_turn_history_replay` |
| 12 | `input: list[Message]` 不消费 session 历史 | ✅ | `test_invoke_list_messages_input_no_session_history` + 流式版 |
| 13 | 创建 KB → ingest → 轮询 task → search 三件套通 | ✅ | `test_ingest_text_and_search` |
| 14 | 本地 agent 通过 `core.knowledge.search_kb()` 拿结果 | ✅ | `test_in_process_search_kb` + `test_echo_with_rag_doc_marker` |

**结果：14 / 14 ✅**

---

## 架构轴

| # | 验收项 | 状态 | 证据 |
|---|---|---|---|
| 1 | agent 子包仅依赖 chameleon-core | ✅ | `grep "chameleon\." chameleon-agents/echo/pyproject.toml` 仅出现 core + providers-base + langgraph |
| 2 | providers 单向依赖 core + base | ✅ | dify/fastgpt/langgraph 的 pyproject.toml 仅依赖 chameleon-core + chameleon-providers-base |
| 3 | 加新本地 agent 不动 app / providers | ✅ | echo 子包独立，registry 启动时 namespace 自动扫到 |
| 4 | 加新 provider 不动 base / 其它 provider / agent | ✅ | 三个 provider 子包相互独立，base 协议稳定 |
| 5 | 所有接口返 `Result[T]` / `PageResult[T]`，无裸数据 | ✅ | grep API 文件均返 `Result.ok(...)` |
| 6 | 全局异常 handler 接管，无业务 try/except 吞异常 | ✅ | `test_global_handler` 全过；service 层仅 try/except 写 call_log 后 raise |
| 7 | DB 全 PG，Alembic 受管，pgvector HNSW 索引就位 | ✅ | `psql \di ix_chunks_embedding_hnsw` 存在；alembic current = 0002 |

**结果：7 / 7 ✅**

---

## 规约轴（python-codebase.md 红线）

| # | 验收项 | 状态 | 证据 |
|---|---|---|---|
| 1 | API 层不写 SQL / 不直接调 Mapper | ✅ | `grep "from sqlalchemy" chameleon-app/.../api.py` 仅 import AsyncSession 用于类型注解 |
| 2 | Service 不返 ORM 给 API（转 schemas DTO） | ✅ | 所有 service 返 `*Item / *Created / PageResult[...]` 等 pydantic 类型 |
| 3 | 类型注解齐全 | ✅ | 所有函数签名带类型；ruff 未报缺类型 |
| 4 | loguru `{}` 占位符，无字符串拼接日志 | ✅ | `grep "f\".*{.*}.*\".*logger\."` 无匹配 |
| 5 | 无 stdlib `logging` 直接使用 | ✅ | `grep "^import logging"` 仅 `logger.py` 内部 InterceptHandler 用 |
| 6 | 无 `print` 调试遗留到生产 | ✅ | grep 无匹配（CLI 用 click.echo，不算调试 print） |
| 7 | `ruff check` 通过（含 isort） | ✅ | `All checks passed!` |
| 8 | alembic 脚本带 `downgrade()` / `--rollback` | ✅ | 0001 + 0002 都有 downgrade 实现 |

**结果：8 / 8 ✅**

---

## 全量数据

```
$ uv run pytest -q
116 passed in 2.73s

$ uv run ruff check .
All checks passed!

$ uv run alembic current
0002 (head)

$ uv run uvicorn chameleon.app.main:app
INFO     | FastAPI app created
INFO     | provider registered | name=dify
INFO     | provider registered | name=fastgpt
INFO     | provider registered | name=langgraph
INFO     | agent registered (local langgraph) | key=echo
INFO     | ─── Chameleon Registry ───
INFO     | Loaded 3 providers: dify, fastgpt, langgraph
INFO     | Loaded 1 agents:
INFO     |   [langgraph] echo                       (built-in)
```

---

## 实施总览

| Phase | Commits | Tasks | 主要产出 |
|---|---|---|---|
| P0 脚手架 | 1 | 5 | uv workspace 7 子包 + Alembic + 最小 FastAPI + PG 复用 |
| P1 chameleon-core | 1 | 9 | config / logger / db / response / exceptions / auth / 8 张共享 ORM |
| P2 Provider 抽象 | 1 | 6 | base + 3 个 provider 适配器 + registry 启动钩子 |
| P3 业务模块（非流） | 1 | 5 | agent / conversation / api_key / admin + CLI init-admin |
| P4 SSE 流式 | 1 | 4 | 序列化 + sse_iter 持久 task + service.stream_invoke + 5 个 E2E |
| P5 向量与知识库 | 1 | 7 | embedding / vector / knowledge + KB CRUD + ingest worker + 9 个 E2E |
| P6 echo + 外部 E2E | 1 | 5 | echo agent 真实 LangGraph + EchoChatModel + 9 个外部 E2E |
| P7 文档 + 验收 | 1 | 6 | README + operations + cli + extension-guide + 本报告 |

**总计**：8 个 commits，47 个 Tasks，约 47 个 Python 模块，116 个测试。

实际工时：1 天集中完成（计划 22.5 工作日；用 Claude Opus 协作压缩到约 1/22）。

---

## 已知限制 / v1 YAGNI 切除（按设计 S6.2）

- ❌ OpenAI 兼容适配层（外部 client 用统一契约即可）
- ❌ Per-embedding-model 多 chunks 表（v1 锁 1536 单维）
- ❌ 流式断点续传
- ❌ Webhook 异步回调
- ❌ 实时配额 / 限流（call_logs 留底 ≠ 实时拦截）
- ❌ 跨进程任务队列（v1 进程内 asyncio.create_task，未来切 Arq）
- ❌ 多租户隔离（个人项目，app_id 仅审计）
- ❌ ProviderCapabilities 元数据
- ❌ Admin 前端 UI
- ❌ Prometheus / OpenTelemetry
- ❌ AI 标题生成（默认前 30 字截断）

详见 [扩展指南](../extension-guide.md) ——v0.2+ 加这些不动现有架构。

---

## 实施期产生的"超出计划"决策记录

| Phase | 决策 | 原因 |
|---|---|---|
| P0 | virtual workspace（无 root `[project]`） | uv workspace 推荐形态 |
| P0 | pytest `--import-mode=importlib` | 跨子包同名 test 文件 |
| P0 | alembic env.py 从 env var 读 URL | 不在 alembic.ini 明文 |
| P1 | `pytest-asyncio` session-scoped loop | asyncpg 跨函数 event loop 问题 |
| P1 | `PermissionError` → `PermissionDeniedError` | 避免 shadow Python builtin |
| P1 | ASGITransport `raise_app_exceptions=False` | 让全局 handler 在测试环境也接管 |
| P2 | `_StreamAggregator` done 字段合并策略 | provider emit done.data 为空时用累积 |
| P2 | FastAPI lifespan 替换 on_event | 0.115 deprecation |
| P3 | `scopes` JSON 列用 Python filter | PG `json ~~ text` 不存在；JSONB 才行 |
| P3 | 跨 app session 返 404 而非 403 | 避免泄漏 session 存在性 |
| P4 | `sse_iter` 持久 task pattern | wait_for 超时会 cancel source 重启的 bug |
| P4 | 流式 service 自管 session | StreamingResponse 期 Depends session 已结束 |
| P4 | service 截胡 provider 的 done | provider 不知 Chameleon session_id |
| P5 | `asyncio.create_task` 替代 BackgroundTasks | 后者在 httpx ASGITransport 测试下不触发 |
| P5 | DeterministicHashEmbedding 测试桩 | 避免真调 OpenAI |
| P6 | EchoChatModel 假 LLM | langgraph stream_writer 不走 astream_events |
| P6 | citations 走 graph state | 比 stream_writer 更 idiomatic |

---

## 后续行动

v1 已具备投入个人使用的能力。建议：

1. **接 1-2 个真实 agent**：把 sage 里跑得好的 data_qa_v2 移植到 `chameleon-agents/`，或在 DIFY 上配几个 agent 通过 `agents.yaml` 接入
2. **接你的第一个消费者应用**：用 `init-admin → 发 app key → 调 echo` 走一遍，再换成真实 agent
3. **观察一周**：看 `call_logs` 流量，发现的问题进 v0.2 backlog

v0.2 候选项（按设计 S6.2 + 实施期记录）：
- OpenAI 兼容层（接 OpenAI SDK 体系的工具如 LangChain / AutoGen）
- 实时限流（Redis token bucket）
- Arq + Redis 替换 asyncio.create_task（量起来后）
- session 维度的语义检索（message embedding worker）
- AI 自动标题生成

---

*v0.1.0 ready for personal deployment.*

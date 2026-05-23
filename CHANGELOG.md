# Changelog

All notable changes to Chameleon. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning follows [SemVer](https://semver.org/).

## [Unreleased]

### Added

- **Sandbox Runtime 抽象 + Mock 实现（P20.1 PR #45）** — `chameleon.core.sandbox`：`SandboxRuntime` ABC + `SandboxConfig` / `SandboxResult` 不可变 dataclass + 全局 registry（`register_runtime` / `get_runtime` / `list_runtime_names`）；`SandboxConfig.__post_init__` 校验 timeout / memory / cpu 上下界 + 拒绝 `network='full'`；`MockSandboxRuntime` subprocess 实现（dev/test 用，`CHAMELEON_ENV=production` 拒绝加载）—— preexec_fn 容错 setrlimit (CPU/AS/NPROC)、`asyncio.wait_for` 强杀超时、stdout/stderr 各 1MB 截断。19 单测 + 1 Linux-only skip（macOS 上 `RLIMIT_AS` 是 no-op）。
- **Docker runtime + bootstrap lifespan（P20.1 PR #46）** — `DockerSandboxRuntime` 用 docker-py SDK 包到 `asyncio.to_thread`；代码 base64 经 env 喂给 `sh -c | base64 -d > /tmp/main.py | python` 避免 attach_socket detach 时的 stdin 死锁；安全默认：`network_mode=none` / `read_only=True` rootfs / `tmpfs=/tmp` / `user=65534:65534` nobody / `cap_drop=ALL` / `no-new-privileges` / `pids_limit=64`；docker 不可达自动降级 mock；`bootstrap_runtimes()` lifespan 启动期注册。7 个 docker smoke 测试真跑 container（hello / 非零退出 / runtime error / timeout 杀容器 / stdout 截断 / network=none 阻塞）。
- **CodeRunnerTool + ToolNode 接通（P20.1 PR #47）** — `chameleon.core.tools.builtins.code_runner.CodeRunnerTool` 调 sandbox runtime；admin config 透传 timeout/memory/cpu/network/image；用户代码非零退出不算 tool fail（数据带 `exit_code` + `user_code_failed` meta）；通过现有 ToolNode → GraphExecutor 链路调度可达，9 个 E2E 覆盖（Tool 层 + Graph 层）。
- **Ed25519 manifest 签名 + registry 协议（P20.2 PR #48）** — `chameleon.core.plugins.signing`：`generate_keypair` / `sign_manifest` / `verify_manifest`（PyNaCl 实现）+ `InvalidSignatureError`；`registry_client`：`fetch_index` 拉远端 `<url>/index.json`（含 publishers pinning + plugins entries 列表）+ `fetch_and_verify_manifest` 对单 plugin 拉 manifest + 签名并按 publisher pubkey 验签；`PluginRegistryEntry` ORM + `plugin_registries` 表（pubkey_pinning + cached_entries 缓存）；新增 `ResultCode.NotFound = 40400` 通用 404 码（之前 eval_jobs/plugins/workspaces 用过但未定义）。9 个签名单测覆盖：roundtrip / tampered 拒绝 / 错 pubkey 拒绝 / 缺签名 / 缺 pubkey / 长度非法 / base64 非法。
- **Marketplace admin API + install_from_remote（P20.2 PR #49）** — `chameleon.system.marketplace`：registries CRUD + `/sync`（fetch + 缓存 publishers/entries 到 DB）+ `/search`（跨所有 enabled registry 缓存搜索 + 标 installed）+ `/install`（按 cached entry 拉 manifest + 验签 + 复用 `plugin_registry.install`）；source='marketplace' 标识来源。
- **Marketplace UI（P20.2 PR #50）** — `/marketplace` 列表 + 卡片网格：上半部 registry 表（同步/启停/删除）+ 下半部 plugin grid（type 彩色 badge + tags chip + 下载数 + 一键安装）；`AddRegistryModal` 注册新 marketplace；sidebar 加 ShoppingBag 图标的「插件市场」入口。7 个 marketplace E2E：CRUD / 去重 / 合法签名全链路 / 篡改 manifest 拒绝 / 未知 publisher 自动 drop / disabled 拒绝 / 搜索过滤。
- **KbCollection schema + chunks 列扩展（P20.3 PR #51）** — `kb_collections` 表（kb_id + collection_type + name + indexes JSONB + config）；chunks 加 `collection_id` (FK ondelete=SET NULL) + `index_name`（default='chunk'）+ `qa_question` + `api_endpoint` + 复合索引；老 chunks `collection_id=NULL` 兼容；`COLLECTION_TYPES = (generic, faq, wiki, api)` 常量 + `DEFAULT_INDEXES`。
- **FAQ / Wiki / API 三套 chunker + dispatch（P20.3 PR #52）** — `chameleon.api.knowledge.chunkers` 子包：`ChunkPayload` 统一形态 + `get_chunker(type)` 注册表 dispatch；`chunk_faq` 按 `## Q:` 切对填 qa_question + 无 Q 头自动回退 generic；`chunk_wiki` 按 `#` heading 切 + heading_path 栈维护 + 单段超 max_chunk_size 再 fixed 子切；`chunk_api` 解析 OpenAPI YAML/JSON 每 endpoint 一 chunk + `api_endpoint` 字段 + tags 过滤 + deprecated 默认跳。14 单测覆盖 dispatch / 三种类型解析 / 回退路径 / 边界。
- **KB collections admin API + 类型不可改红线（P20.3 PR #53）** — `chameleon.system.kbs.collections_service`：list / create / update / delete + `get_or_create_default` 兜底；`UpdateCollectionRequest` 不含 `collection_type` 字段（红线 plan §2 P20：类型一经写入不可改，必须新建 collection + 重新 ingest）；同 KB 内 name 唯一；删除走 ondelete=SET NULL 保留 chunks。6 E2E：CRUD / 去重 / 未知 type 拒绝 / type 改不动 / 删 / 跨 KB 隔离。
- **KB Collections tab UI（P20.3 PR #54）** — `/kbs/:id` 详情页加 Collections tab（Layers 图标）：列 collections 表 + 类型彩色 badge + 索引拓扑展开 + 删除；新建 modal 选类型（4 种 + 提示文案）+ 红色横幅警告"类型一经写入不可改"；通过现有 admin auth + apolloy queryClient 缓存。

## [0.5.0] — 2026-05-23

**P19 阶段三收官**：Eval 自动化 + Plugin 热加载生态 + Multi-tenant Workspace + Multimodal。十三个 PR 一次性把"实用性脚手架"补齐：能 cron 跑回归测；能在线热装/启停插件；能用 workspace 切租户视角并加配额闸门；能在 Playground 上传图音文件参与多模态对话。

### Eval 自动化（P19.1）

- **Eval Jobs schema + APScheduler 触发器（PR #30）** — `eval_jobs` / `eval_job_runs` 两张表；`AsyncIOScheduler` lifespan 接入，CRUD 后路由层 `sync_job` 自动注册/卸载 cron；手动 `/trigger` 端点同步复用 `datasets.runner` 跑一次 + 写 `eval_job_run` + 计算 `delta_score`。
- **Slack / Webhook notifier + regression alert + Redis dedup（PR #31）** — Notifier ABC + 内置两类渠道；`should_alert` 阈值判定；`maybe_send_alert` Pipeline 集成进 `trigger_job` 末尾；Redis `SET NX EX(silence_minutes*60)` 防风暴去重；网络失败 `alert_sent=False`，主路径不受影响。
- **Eval Jobs 管理 UI（PR #32）** — `/eval-jobs` 列表 + 详情页（8 张概览卡 + SVG 趋势折线 + 运行历史表）；create/edit modal cron 预设 + 自定义双轨；sidebar 新增「评测任务」入口。

### Plugin Hot Loader（P19.2）

- **Plugin manifest 协议 + Registry 骨架（PR #33）** — `PluginManifest` Pydantic 严格模型（正则校验 + `extra='forbid'` + 拒绝 `__import__`/`eval`）；`plugin_instances` 表；`PluginRegistry` 单例（bootstrap_builtin / load_all / set_enabled / reload / install / uninstall），5s asyncio.wait_for 超时；builtin local/dify/fastgpt 首次启动 idempotent seed；`build_provider_registry()` 接受 `disabled_plugin_keys` 实现 admin disable builtin 不重启即生效。
- **SDK 装饰器 + Admin API + sandbox（PR #34）** — `@plugin_provider` / `@plugin_tool` / `@plugin_embedding` + `assert_entrypoint_not_internal` 沙箱拒绝指向 `chameleon.core.models` / `infra` / `system` / `api` / `app` 等内部模块；`/v1/admin/plugins` 完整 CRUD + reload + uninstall + config 更新；启停后重建 PROVIDERS。
- **Plugin 管理 UI（PR #35）** — `/plugins` 列表（内置 / 外部分组 + type 彩色标签）；安装 modal 粘贴 manifest JSON 实时解析；config modal JSON 编辑 + 顶部 schema 字段提示。

### Multi-tenant Workspace（P19.3）

- **Workspace schema + default ws seed（PR #36）** — `workspaces` / `teams` / `memberships` / `workspace_quotas` 4 张新表；`WorkspaceScopedMixin` 给 10 张业务表（agents/apps/knowledge_bases/graphs/datasets/eval_jobs/tool_instances/channels/abilities/embed_configs）加 NULLABLE `workspace_id`；alembic upgrade 内幂等 seed default workspace (id=1) + UPDATE backfill 老数据。
- **鉴权 + 业务过滤（PR #37）** — `CurrentUser` 扩展 `workspace_id` / `workspace_scope` / `is_admin` / `workspace_filter_ids`；`X-Workspace-Id` header 切换视角；agents 路由首批接通过滤；isolation 测试 6 场景。
- **Workspace admin API + 切换 UI + Members（PR #38）** — `/v1/admin/workspaces` CRUD + members CRUD；Zustand workspace-store + axios interceptor 自动注入 `X-Workspace-Id`；`WorkspaceSwitcher` dropdown + 切换时 `queryClient.clear()`；`/workspaces/:id/members` 页 inline role 改 + 邀请 modal。
- **配额限流 + 月度 reset cron（PR #39）** — `quota_service` 单点：业务 invoke 前 check token 月配额 + 请求日配额，超额 → HTTP 429；`record_call` trace 根累加；lazy + cron 双轨跨期 reset（APScheduler 每日 00:05 UTC）；`CurrentApp.workspace_id` 由 auth dep JOIN apps 解析；admin API + 前端 `QuotaCard` 双 usage bar。

### Multimodal（P19.4）

- **ContentBlock 协议 + ProviderMessage 扩展（PR #40）** — `TextBlock` / `ImageUrlBlock` / `AudioUrlBlock` 三类 ContentBlock + `normalize_content` / `flatten_to_text` helper + `Message.content` 联合类型 `str \| list[ContentBlock]`（OpenAI/Anthropic 兼容）；`messages.content_blocks` JSONB 列；`SSEEventKind` 加 `image_chunk` / `audio_chunk` 预留；echo native agent 检测 ImageUrlBlock。
- **MinIO presigned upload + ingest（PR #41）** — `/v1/files/presigned-upload` 生成临时 PUT URL + 长效 GET URL；`/v1/files/{object_id}/finalize` stat 确认 + size mismatch 拒绝；20MB 上限 + mime 白名单；object_id 用 `secrets.token_urlsafe(16)` 防猜测 + namespace 隔离 + path traversal 剥离。
- **Playground 多模态上传 UI（PR #42）** — `file-upload` helper 三步走；`FileAttachButton` + chip 缩略；ChatColumn 集成 attachments → 发送时转 `ContentBlock[]`；MessageBubble 渲染 image 缩略 / audio inline；`/v1/files` 加 `current_app_or_admin` 双轨鉴权。

### 红线（P19 新增）

- ⛔ Plugin 加载必须 async + 5s 超时；manifest 不允许包含可执行代码；plugin 不能直接挂载 `chameleon.core.models.*` 等内部模块
- ⛔ Multi-tenant 改 schema 必须 backward-compat（workspace_id NULLABLE + default ws backfill）
- ⛔ Eval alert 必须 Redis rate-limit + dedup；告警失败不污染主 trigger 路径
- ⛔ 配额检查走单点中间件（assert_within_request_quota），业务路由不分散写
- ⛔ Multimodal image / audio 走 URL，不内嵌 base64
- ⛔ 切换 workspace 强制 `queryClient.clear()` 防跨租户缓存污染

### 测试

- P19 专属 130/130 全绿（含 eval_jobs / plugin / workspace / quota / multimodal / files）
- 全套 pytest 589 passed（剩 12 pre-existing failures 与 P19 无关）

## [0.4.0] — 2026-05-23

**P18 阶段二收官**：可视化工作流 + Tool 协议 + Eval 闭环。Dify 风 GraphEngine MVP + OpenAI function calling 对齐 + LangFuse 风 dataset/run 评估链路 + FastGPT 风 chunking 实时预览。

### Workflow（P18.1）

- **GraphEngine 内核** — `chameleon.core.graph`：泛型 `Node[InputT,OutputT]` 抽象 + Kahn 拓扑排序 + 串行 DAG 执行 + 错误冒泡。
- **5 类内置 node** — start / end / noop / **llm** / **kb** / **tool** / **if_else**。LLM/KB 都接到 P17 的 router + KB search；IfElse 用 jsonlogic 风简化表达式（var / 比较 op / and/or/not）。
- **React Flow 编排器** — `/graphs`：列表 + 新建 + 软删；`/graphs/:id/edit`：3-pane（左 palette / 中画布 / 右 inspector）+ Test Run / Run 双轨。
- **GraphRun 持久化 + trace 串联** — `graph_runs` + `graph_node_runs` 两张表；每节点写 child call_log 串到 P17.C1 trace tree drawer，admin 端可直接复用嵌套树视图。

### Tools（P18.2）

- **Tool 协议** — `chameleon.core.tools.Tool` 基类 + 全局 registry + `parameters_schema` JSON Schema 校验 + `ToolResult` 标准返回。
- **内置 HTTP/SQL Tool** — HTTPTool（GET/POST + URL 白名单 + timeout + max_bytes）；SQLTool 默认 disabled（admin 显式开），强制 SELECT/WITH + 禁 DML/DDL + 白名单 db_url + 30s 超时。
- **tools admin** — `/v1/admin/tools` CRUD + `/catalog` 列内置 + ToolInstance 表持久化 (tool_key, config, enabled)。
- **ToolNode 闸门** — 跑前查 tool_instances，disabled 则拒绝 + 清晰错误。
- **LLM function calling** — LLMNode `tool_keys=[...]` 启用 OpenAI tools 协议；模型决定调谁返 tool_calls 结构化数组（不自动执行，留给后续 ToolNode）。

### Eval（P18.3）

- **Dataset 一键采样** — `/v1/admin/datasets/{id}/sample-from-logs` 按 filter 批量采 call_log → dataset_items。强制脱敏：string 字段 → `{hash:sha256(16chars), length, token_count_approx, preview(80字符)}`，**绝不存原始 PII**。
- **人工标注** — `POST /datasets/items/{id}/update` 修改 expected_output（金标准）/ meta。
- **DatasetRun** — `POST /datasets/{id}/run` 持久化跑：model_override + prompt_override + judge（exact_match / contains / llm_judge stub）；每 item 调 LLM 拿 actual_output → judge 评分 → 写 dataset_run_items + Score(source='eval')。
- **对比能力** — `POST /datasets/runs/compare` 跨 N 个 run（同 dataset）item-by-item 横向 diff，便于 prompt 调参 / model A/B 测试。

### RAG（P18.4）

- **Chunking 实时预览** — `/v1/admin/kbs/chunking-preview` 不写库，纯调试；前端 `/kbs/:id/chunking-preview` 三栏 UI（左原文 / 中 chunks 卡片 / 右策略表单），300ms 防抖自动跑预览。5 种 mode 全支持。

### Chat（P18.5）

- **Message 分支** — messages 加 `parent_message_id` 列 + 索引；regenerate / edit-and-resend 时新增不覆盖，UI 按 parent_message_id 聚类显主线 + 分支。Agent 中间步骤复用 P17.C1 trace tree drawer。

### Migrations

新增 alembic 脚本：
- `p18_w9_graphs` — graphs + graph_runs + graph_node_runs
- `p18_w12_tools` — tool_instances
- `p18_w13_datasets` — datasets + dataset_items
- `p18_w13_dataset_runs` — dataset_runs + dataset_run_items
- `p18_w15_message_branch` — messages.parent_message_id

### Breaking changes

无破坏性改动；老 routing / call_logs / scores 路径全部保留。
具体迁移步骤见 `docs/release/v0.4-migration.md`。

### Known limitations

- GraphEngine 当前串行执行；并发 fanout / merge 节点留 P19
- Tool Code Sandbox 占位，不安全的代码执行能力暂不开放
- llm_judge 返固定 0.5，真 LLM 评分逻辑留 P19
- Message 分支 UI 仅 playground 有 in-memory 版（P17.E1），DB 持久化基底已就位但端到端 UI 流程留 P19
- Chunking 策略版本化（changelog）留 P19

---

## [0.3.0] — 2026-05-23

**P17 阶段一收官**：Gateway / Trace / RAG / UI 四维齐升级。LangFuse 风嵌套 Observation + One-API 风路由矩阵 + Dify 风外观主题 + LobeChat 风消息 Actions 同步落地。

### Foundation

- **JSON Schema 引擎** — provider/agent 配置都用 schema 驱动；admin `/v1/admin/schemas` 暴露 registry，前端 `JSONSchemaForm` 自动渲染表单。`/dev/schemas` 提供调试页。
- **Typed SSE event registry** — 后端有 helper 强类型化 `meta/delta/citation/end/error/tool/usage` 事件，前端 TS 镜像保证端到端类型对齐。

### Gateway

- **Channels 表** — 一个 provider 可有多 channel（不同 key/base_url/quota/优先级），admin CRUD + 加密落库 + 软删 + 自动回填 default channel。
- **Abilities 矩阵** — `(group_id, model_code, channel_id)` 联合唯一；调用方按 `model_code` 路由到 channel，支持 priority + weight 加权随机。
- **Failover wrapper** — channel 失败自动切下一优先级，EWMA 响应时间统计 + fail_count 超阈值自动 `auto_disabled`；admin 切回 `enabled` 时 fail_count 归零。

### Trace

- **嵌套 Observation** — `call_logs` 扩 `parent_id / observation_type / completion_start_ms`；9 类（trace/span/generation/agent/tool/retriever/evaluator/embedding/guardrail）对齐 LangFuse。`observe()` async context manager 自动维护父子链路。
- **Trace tree API + UI** — `GET /v1/admin/call-logs/{request_id}/tree` 返嵌套结构；call_logs drawer 新 Tree tab 默认展开，按类型配色 + duration 条 + token badge。
- **Scores + Feedback** — 新增 `scores` 表（append-only），admin 可写人工标注；widget `/v1/embed/{key}/feedback` 落 source='feedback' 行；trace tree 节点行内渲染 ScoreBadge。

### RAG

- **TokenChunker（model-aware）** — `chunk_strategy.mode='token'` 启用 tiktoken；自动按 KB.embedding_model 选编码器，未知 model fallback `cl100k_base`。KB 配置页 5-mode picker，token 模式单位切到 token。

### UI

- **消息 hover Actions** — playground + widget 双边：copy / regenerate / edit（user）/ 👍 / 👎 / delete。playground stale 老 assistant 灰显保留；widget user 消息 hover 才显 Actions。
- **多色主题** — 8 primary（深蓝 / 紫罗兰 / 森林绿 / 日落橙 / 玫瑰红 / 青湖蓝 / 琥珀金 / 碧海绿）× 4 neutral（暖石灰 / 石板蓝 / 锌灰 / 中性灰）× 3 animation（无 / 柔和 / 敏捷）。preferences store 持久 localStorage，无需重新加载即时生效。Settings 加 "外观" tab。

### Migrations

新增 alembic 脚本：

- `p17_w3_channels` —— channels 表 + 索引 + 默认 channel 回填
- `p17_w4_abilities` —— abilities 矩阵表 + 联合唯一索引
- `p17_w4_agent_model_code` —— agents 加 `model_code` 字段
- `p17_w6_observation` —— call_logs 加 parent_id / observation_type / completion_start_ms
- `p17_w6_channels_cascade` —— channels.provider_id FK 改 CASCADE
- `p17_w7_scores` —— scores 表

### Breaking changes

无破坏性改动；老的 `provider_id` 直绑路由仍可用（feature flag `routing.use_abilities=false`）。
具体迁移步骤见 `docs/release/v0.3-migration.md`。

### Known limitations

- TokenChunker 当前不感知段落 / 句子边界（直接按 token 窗口切），多策略组合留 P18.D2
- Dark mode 仅占位（`themeMode='dark'` 不生效），P18 实施
- Widget 反馈写入失败仅静默 console.warn，不向用户告警

---

## Earlier

更早历史合并到 `docs/changelog-archive/` —— 0.2.x 之前的 release notes 保留在 git history 与各 P 阶段计划文档。

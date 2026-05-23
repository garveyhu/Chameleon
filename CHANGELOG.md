# Changelog

All notable changes to Chameleon. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning follows [SemVer](https://semver.org/).

## [Unreleased]

### Added

- **Eval Jobs schema + APScheduler 触发器（P19.1 PR #30）** — `eval_jobs` / `eval_job_runs` 两张表；`AsyncIOScheduler` lifespan 接入，CRUD 后路由层 `sync_job` 自动注册/卸载 cron；手动 `/trigger` 端点同步复用 `datasets.runner` 跑一次 + 写 `eval_job_run` + 计算 `delta_score`。
- **Slack / Webhook notifier + regression alert + Redis dedup（P19.1 PR #31）** — Notifier ABC + 内置两类渠道；`should_alert` 阈值判定（`abs(delta) >= regression_threshold` 触发）；`maybe_send_alert` pipeline 集成进 `trigger_job` 末尾；Redis `SET NX EX(silence_minutes*60)` 防风暴去重；网络失败 `alert_sent=False`，主路径不受影响。
- **Eval Jobs 管理 UI（P19.1 PR #32）** — `/eval-jobs` 列表页（job_key/cron/最近分数/状态/手动触发/启用切换/删除）；`/eval-jobs/:id` 详情页（8 张概览卡 + SVG mean_score 趋势折线 + 运行历史表，alert sent 高亮）；create/edit 复用同一 modal，cron 用预设 + 自定义双轨，alert_config 启用切换出 Slack/Webhook 渠道配；sidebar 新增「评测任务」入口（AI 能力分组）。
- **Plugin manifest 协议 + Provider hot reload 骨架（P19.2 PR #33）** — `chameleon.core.plugins`：`PluginManifest` Pydantic 严格模型（name/version/entrypoint 正则校验 + `extra='forbid'` 防走私 + 拒绝 `__import__`/`eval` 等敏感关键字）；`plugin_instances` 表（builtin/local/git/pypi 四种 source）；`PluginRegistry` 单例（bootstrap_builtin / load_all / set_enabled / reload / install / uninstall），5s asyncio.wait_for 超时上限；builtin local/dify/fastgpt 首次启动 idempotent seed；`build_provider_registry()` 接受 `disabled_plugin_keys` 实现"admin disable builtin plugin 不重启即生效"。
- **Plugin SDK + Admin API（P19.2 PR #34）** — `chameleon.core.plugins.sdk` 暴露 `@plugin_provider` / `@plugin_tool` / `@plugin_embedding` 装饰器给外部开发者；`assert_entrypoint_not_internal` 沙箱拒绝把 entrypoint 指向 `chameleon.core.models` / `chameleon.core.infra` / `chameleon.system` / `chameleon.api` / `chameleon.app` 内部模块；`/v1/admin/plugins` 端点齐全（list / get / install / enable / disable / reload / uninstall / config 更新）；启停后调 `reset_registry_for_test + init_registry` 让 PROVIDERS 实时下架/恢复 builtin；新增 `plugins:read/write/delete` 权限点 seed。
- **Plugin 管理 UI（P19.2 PR #35）** — `/plugins` 列表页（内置 / 外部 两个分组，type 标签彩色，状态 badge，操作 reload/启停/卸载/编辑 config；builtin 卸载按钮置灰带 tooltip）；`PluginInstallModal` JSON manifest 粘贴 + 实时解析预览 + source local/git/pypi 切换；`PluginConfigModal` JSON 编辑器 + 顶部 manifest config_schema 字段提示；sidebar 加 Puzzle 图标的「插件」入口（AI 能力分组）。
- **Multi-tenant Workspace schema + default ws seed（P19.3 PR #36）** — `workspaces` / `teams` / `memberships` / `workspace_quotas` 4 张新表；`WorkspaceScopedMixin` 给 10 张业务表（agents / apps / knowledge_bases / graphs / datasets / eval_jobs / tool_instances / channels / abilities / embed_configs）加 NULLABLE `workspace_id` 列 + FK + index；alembic upgrade 内幂等 seed `default` workspace (id=1) + `workspace_quotas` 行 + UPDATE backfill 老数据；service 层鉴权 / 切换 / 配额 UI 推 PR #37-#39。
- **Workspace 鉴权 + 业务过滤（P19.3 PR #37）** — `CurrentUser` 扩展 `workspace_id` / `workspace_scope` / `is_admin` / `workspace_filter_ids`；`get_current_user` 启动时拉 memberships 算可访问 ws 集，支持 `X-Workspace-Id` header 切换视角（`all` 显式全量）；非 admin 越权访问报 403，老用户无 memberships 兜底 default ws；agents 路由首批接通过滤（list 加 `workspace_id IN scope` + DEFAULT 兼容老 NULL 行；create 强制写当前 ws）；isolation 测试覆盖 6 个场景。
- **Workspace admin API + 切换 UI + Members 管理（P19.3 PR #38）** — 后端 `/v1/admin/workspaces` CRUD（默认 ws 防删 + workspace_key 唯一 + 同步 quota 行）+ `/members` CRUD（防重 + role 切换）；前端 Zustand `workspace-store` 持久化当前 ws + axios request interceptor 自动注入 `X-Workspace-Id`；sidebar 顶部加 `WorkspaceSwitcher` dropdown（全量 / 单 ws 切换 + 新建 + 跳成员页）+ 切换时 `queryClient.clear()` 全量 refetch；`/workspaces/:id/members` 页（成员表 + role inline 改 + 移除 + 邀请 modal）；新增 `workspaces:*` 权限点 seed。Chrome MCP 验收切 ws 后 agents 列表立刻按租户过滤。
- **Workspace 配额限流 + 月度 reset cron（P19.3 PR #39）** — `quota_service` 单点：`assert_within_request_quota`（业务 invoke 入口前 check token 月配额 + 请求日配额，超额抛 `WorkspaceQuotaExceeded` → HTTP 429）+ `increment_usage`（`record_call` 钩子在 trace 根累加；子 span 不重复）+ lazy + cron 双轨跨期 reset（跨日清 request_used / 跨月清 token_used；APScheduler 注册每日 00:05 UTC 兜底）；`CurrentApp` 加 `workspace_id` 字段（auth dep JOIN apps 解析）；admin `/v1/admin/workspaces/{id}/quota` GET/update（管理员可设上限或强制重置 used）；前端 `QuotaCard` 双 usage bar（红/黄/蓝渐变 + 超额高亮）+ 上限编辑表单，挂在 members 页顶部。

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

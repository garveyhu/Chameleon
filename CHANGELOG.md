# Changelog

All notable changes to Chameleon. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning follows [SemVer](https://semver.org/).

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

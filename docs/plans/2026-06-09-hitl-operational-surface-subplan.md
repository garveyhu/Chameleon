# HITL 运营闭环（playground / embed / sessions）—— 细化子方案

> 目标：让 **durable / 人在环（ctx.ask_human）agent 在前端真正可用**——不止 dev 端点能 resume，
> 而是 playground 测试、嵌入式 widget、会话/详情运营侧都能「看到暂停 → 回填答案 → 续跑」。
> 这是「完善前端对齐后端 agentkit」里唯一**真功能缺口**（MCP/A2A/媒体/沙箱在前端是服务端透明跑通；
> 只有 HITL 暂停-恢复缺前端闭环）。多层全栈，先出方案后分片实现。

## 0. 现状（调查结论，文件级）

- **provider 层已就绪**：`providers/local/agentkit_runner.py` 的 `run_agentkit` 已 `except AgentPaused`
  → 落 pending（AgentMemory `__chm_pending__`，scope=run_id）+ emit `human_input_pending` step 事件。
- **dev 路径已闭环**：`api/dev/service.py` `dev_call_agent` 支持 run_id + resume_answer，服务端
  `_read_pending` 读 call_index（评审17 #3）+ context_vars 注入 → journal 重放续跑。
- **主路径全缺**：`system/playground/service.py` `invoke_stream`→`_stream_agent`、嵌入式 embed、
  通用 agent invoke **都不接 resume 参数**；前端 playground/embed **不渲染 human_input_pending、无回填入口**。
- **scope 红线**：durable 需 scope_ref；playground/embed invoke 已有 session_id 作 scope，durable 会激活。

## 1. 分层归属决策（先定，免重复/up-dependency）

`_read_pending`（读 AgentMemory pending 的 call_index + 原始 query）目前私有在 `api/dev/service.py`。
playground 在 system 层、embed 在 api 层——都要用。**决策：把 resume 解析下沉到 aikit/util**
（`aikit/tasks/...` 不合适，它是 LLM 任务；放 `aikit` 顶层 util 或 engine/agent）——`resolve_resume(target, run_id)
→ (call_index, original_query)`，dev/playground/embed 共用，避免 system↔api 互依赖。

## 2. 分片实施

### Slice 1（后端·主路径 resume 贯通）
- 抽 `resolve_resume(agent_key, run_id) -> ResumeSpec(call_index, query)`（复用 dev 的 `_read_pending`
  逻辑，下沉到共享层），dev_call_agent 改用它。
- `invoke_stream` + `_stream_agent`（playground）+ 通用 agent invoke 加 `resume_run_id` / `resume_answer`
  入参 → 构造 InvokeContext 时：`request_id=session_id=resume_run_id`（durable scope）+ context_vars
  注入 `_resume_call_index`（服务端读，**不信客户端**）/ `_resume_answer`，原始 query 用 pending 存的。
- 验：playground 调 example-hitl → 暂停（human_input_pending 进 SSE）→ 带 resume 重调 → 续跑完成。

### Slice 2（前端·playground HITL UI）
- `playground` SSE 处理：识别 `human_input_pending` 事件（type=step, name 含 pending / data.prompt）→
  渲染「⏸ 等待人工输入：<prompt>」+ 输入框 + 提交按钮（而非静默卡死）。
- 提交 → 再次 `streamInvoke`，带 `resume_run_id`（= 上轮 session/run_id）+ `resume_answer`。
- 续跑结果接回同一对话流（complete 重放不重调，总结一致）。

### Slice 3（前端·嵌入式 widget HITL）
- `frontend/embed/` widget：input-required 渲染（prompt + 回填框）+ resume 调用，复用 Slice 1 后端。
  终端用户（非运营）也能在嵌入场景完成审批。

### Slice 4（运营·会话/详情 待人工处理）
- 列「暂停中的 durable run」（扫 AgentMemory `__chm_pending__`）：新增只读端点
  `GET /agents/{id}/pending-runs`（或会话维度）→ 运营在详情/会话 tab 看到 pending + prompt + 回填续跑入口。
- 让运营不必进 playground 也能处理积压的人工审批。

## 3. 红线 / 复用

- resume 一次性（评审20）：`_seed_resume` 已防决策翻转，主路径复用同机制，不重复造。
- call_index 服务端权威读（评审17 #3），客户端只提交答案。
- 原始 query 重放（避免 ctx.query 变 → complete 指纹不符），pending 已存 query。
- 每片 ruff/tsc/eslint + 单测 + 起 7009 真实 e2e（example-hitl 经 playground 暂停→回填→完成）+ 浏览器截图。

## 4. 顺序

Slice 1（后端地基，解锁全部）→ Slice 2（playground，最高频测试场景）→ Slice 4（运营待办，价值高）
→ Slice 3（embed，终端场景）。Slice 1 是其余的前提。

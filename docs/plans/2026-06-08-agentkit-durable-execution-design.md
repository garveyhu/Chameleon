# agentkit durable execution / checkpoint·replay —— 细化设计

> 状态：实现级设计，待 review → 分片实施。最后一块品类地基（评审3 #5 / 路线图 T2-8·T5-3）。
> 定位：让 agentkit 自由代码 handle 支持 **HITL 暂停/恢复 + 崩溃恢复**——可复现是调试/评测/
> 事故复盘/人在环的共同地基（对标 Temporal durable execution / LangGraph time-travel）。

## 0. 诚实划界（决定方案）

- **图引擎已有 durable HITL/resume**：`human_input_pending`（FK graph_runs + resume_state=
  {node_id:output} 作节点级重放 seed）+ 图 resume。**需要强 durable/HITL 的场景，建议用图**
  （graphs-as-agents，已是 source='graph' 的 agent）。
- **agentkit 自由 handle 的根本限制**：handle 是自由 async generator，**运行中协程状态不可
  序列化**——无法像图那样存"执行到哪一步"。故 agentkit 的 durable 只能走 **memoization 式
  重放**（re-run + 记忆外部调用），不是真·暂停协程。

## 1. 模型：memoization 式确定性重放（Temporal 套路）

handle 重跑时，每个 ctx 外部调用（complete/stream/run_with_tools/kb/call_agent/ask_human）
按**调用序号**返回首跑记录的结果，使 handle 确定性地重达同一状态再继续：

```
第一次跑：ctx.complete#0 → 真调模型，记 output[0]
          ctx.ask_human#1 → 无答案 → 持久化 pending(call_index=1, prompt) + 抛 AgentPaused
                          → 本次 invoke 以 status=paused 结束
人工回填 → resolve(call_index=1, value=答案)
恢复跑：  ctx.complete#0 → 返记忆 output[0]（不重调模型！确定性 + 省钱）
          ctx.ask_human#1 → 返已回填的答案 → 继续
          ctx.complete#2 → 真调（新调用）→ 记 output[2]
          ...直到完成 或 下一个 ask_human
```

**确定性契约（作者须知）**：handle 在两次重跑间的控制流必须仅由 ctx 调用结果决定——禁用
`random`/`time.now()`/外部副作用做分支（与 Temporal workflow 约束一致；文档明示）。非 ctx
的纯计算可重跑。

## 2. 落库（复用 + 泛化 human_input_pending）

- 新增 `agent_runs`（运行头：id / agent_key / session_id / status[running|paused|done|failed] /
  created_at）作恢复锚（类比 graph_runs）。
- `ctx_call_journal`（或复用 call_log 子行）：{run_id, call_index, method, output_json} —— 首跑
  记每个 ctx 调用结果，重放按 (run_id, call_index) 取。
- HITL pending：复用 `human_input_pending` 但把 FK 从 graph_runs 泛化为 run_id（或加
  agent_run_id 列）；resume_state 不再是 {node_id:output} 而是 journal 的 run_id 引用。

## 3. ctx API

```python
ans = await ctx.ask_human("请审批该操作", schema={...})   # 暂停点：无答案抛 AgentPaused
await ctx.checkpoint("progress", {"done": 3})              # 崩溃恢复：存 author 状态（幂等）
state = await ctx.restore("progress", default={})
```

- `ask_human`：journal 无该 call_index 答案 → emit human_input_pending 事件 + 抛 AgentPaused
  → provider 把 invoke 标 paused、持久化 pending。有答案（resume）→ 返答案。
- `checkpoint/restore`：author 显式存/取 durable 状态（不依赖重放确定性，崩溃恢复兜底）。

## 4. 运行时编排

- `run_agentkit`：包一层 durable runner —— 首次 invoke 建 agent_runs(running)；handle 跑时
  ctx 调用经 journal 记录；遇 AgentPaused → 标 paused + 落 pending + 流结束（status=paused，
  emit pending 事件给前端渲染审批表单）。
- resume endpoint（复用 graph human-input resolve 的 API 形态）：收 (run_id, value) → 写
  journal answer + 重新 invoke handle，ctx 调用走 journal 重放 → 跑过 ask 点继续。
- 与统一成本闸：重放的记忆调用**不重复计费**（不真调模型）；只新调用计费。

## 5. 分片实施
1. **Slice 1**：agent_runs + ctx_call_journal + memoization 重放底座（ctx.complete 记/放，
   单测：同一 run 重跑返记忆值不重调）。
2. **Slice 2**：ctx.ask_human + AgentPaused + provider 标 paused + 落 pending（复用
   human_input_pending）。e2e：ask→paused→resolve→resume 续跑。
3. ✅ **Slice 3（已交付，170949e 后续）**：ctx.checkpoint/restore（崩溃恢复 author 状态）。
   migration-free——复用既有 ctx.memory 持久化（AgentMemory 表）+ 保留键 __chm_checkpoint__，
   跨所有 transport 可用。Slice 1/2（journal 重放 + ask_human）仍需新 agent_runs/journal 表
   （待迁移窗口）。
4. **Slice 4**：前端审批 UI（复用图 human-input 表单）+ 超时（复用 APScheduler 扫 timeout）+
   stream/run_with_tools 的 journal 记录。

## 6. 红线 / 验收
- 确定性契约违反（控制流依赖非 ctx 随机性）→ 重放可能分叉到不同 call_index，文档强警告 +
  journal 校验 method 不匹配时报错而非静默错乱。
- 重放不重复计费 / 不重复副作用（工具调用记忆，不重跑 http POST 等）。
- 每片 ruff/lint + 单测 + 真实 e2e（ask→resume 续跑）+ 聚焦 commit。

## 7. 取舍备注
- 这是"够用的 durable"：HITL + 崩溃恢复 + 省钱重放，不是图那样的可视化 time-travel/分叉。
  需要后者用图。两条 authoring 路线（代码 agentkit / 可视图）各擅其长。
- 工作量大（journal + 重放 + pending + resume 端点 + 前端）；属多分片专注项，非单周期。

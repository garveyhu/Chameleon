# 可观测溯源 LangSmith 化重构

> 2026-05-29 · 把 call_logs 做成跨应用统一的 LangSmith 式 trace 真相源；graph 节点接进
> trace 树、根行补 model/cost；观测域拆 Trace / Session 两 tab；删冗余的 graph_node_runs。

## 背景与痛点

对话型编排（graph）应用调用后，运行记录里 **模型 / TOKEN 数 / 成本全是「—」**，
trace 树是「扁的」（根 → 一堆平铺 generation），看不到节点层级。根因三处：

1. **graph 节点轨迹没进 call_logs**：节点（classify_intent / select_tables…）落在
   独立的 `graph_node_runs` 表，不写 call_logs span 行，且不记 model/token/cost。
   LLM generation 行（GenerationRecorder 落的）直接挂在**根 trace** 下，不挂在所属节点下。
2. **graph 根行 model/cost 丢失**：provider 跑完不回收 usage → 根行 model_code/cost_usd
   落 NULL；`aggregate_generation_usage` 只补了 token（子行 SUM），没补 model 和 cost。
3. **两条执行路径产出结构不一致**：`runner.py`（编辑器 test-run）**手动**给每个节点写
   call_log（且 llm 节点 → generation，与 GenerationRecorder 回调**双写重复计费**）；
   provider 路径只写 graph_node_runs，不写 per-node call_log span。

## 现状盘点（好消息：底子已是 LangSmith 形状）

- **数据模型**：`call_logs` 单表 + `observation_type` 枚举（trace/span/generation/agent/
  tool/retriever/…）+ `parent_id` 自引树，带齐 model_code / prompt_tokens /
  completion_tokens / cost_usd / duration_ms / completion_start_ms / spans /
  request_payload / response_payload。定义在 `core/models/api_key.py`，p17_w6 加的嵌套字段。
- **采集**：`GenerationRecorder`（LangChain AsyncCallbackHandler）烧进每个 LLMFactory
  实例，任何 .ainvoke()/.astream() 自动落 generation 行。**关键**：`llm_recorder.py:224`
  `parent_id = current_observation_id() or tc.request_id` —— 已经优先读
  `_CURRENT_OBS_ID` ContextVar。
- **嵌套上下文**：`core/observe/context.py` 已有 `observe(...)` 上下文管理器 +
  `_CURRENT_OBS_ID` 栈 —— 进 span 入栈、退栈复位，正是「current span」语义。
- **查询**：`/v1/admin/call-logs` 列 parent_id IS NULL 根；`/call-logs/{id}/tree` BFS
  组树 + `aggregate_rollups` 自底向上 SUM cost/token。
- **前端**：`system/traces/` 甘特瀑布 + cost-label；`system/call_logs/` observation-tree +
  trace-drawer + session-ledger-page（即「会话 & 运行」列表）。

→ 缺的不是基础设施，是「把 graph 节点接进 observe() 链」+「根行补 model/cost」+「UI 拆分」。

## graph_runs / graph_node_runs 的定位（删前必读）

| | graph_runs | graph_node_runs | call_logs |
|---|---|---|---|
| 角色 | 运行头 **+ human-input 暂停/恢复的可恢复状态锚** | 节点明细（进出/耗时） | LLM 调用 / span（带 model/token/cost） |
| 读者 | 编辑器 日志/监测 + resume 逻辑 | 编辑器 日志详情 | 全平台观测域 |
| 含钱 | ❌ | ❌ | ✅ |

- **`graph_node_runs` 删** —— 节点明细 call_logs span 全覆盖（还多带 model/token/cost）。
- **`graph_runs` 留** —— `HumanInputPending.graph_run_id` FK→graph_runs（CASCADE），暂停
  时存 `resume_state`（已完成节点输出快照），恢复时 Orchestrator 拿它 seed 继续跑。
  call_logs 是只读观测日志，没有「可恢复执行状态」语义，替代不了（类比 LangGraph 的
  checkpointer vs trace 分离）。

## 设计主张

```
留 graph_runs（resume 锚 + 运行头）
删 graph_node_runs（→ call_logs span 全覆盖）
call_logs = 唯一 trace 真相源
```

## 分期

### P1 引擎统一发 span（核心）
- TraceContext / observe 已就绪，无需改 GenerationRecorder。
- graph **引擎（orchestrator）** 执行每个节点时包 `observe(observation_type=<按节点类型
  映射>, name=node_id, request_id=f"{root_rid}.{node_id}")`，并落一条 call_log span 行
  （node_id/node_type 入 meta/payload，input/output/duration/status）。
  - 节点类型→observation_type 映射沿用 runner._NODE_TO_OBSERVATION_TYPE：
    llm→generation? **不**：节点壳一律 span，llm 节点内部的 .ainvoke() 由 GenerationRecorder
    落 generation（嵌在 span 下）。kb→retriever、tool→tool、其余→span。
  - record_call 在 core 层用 lazy import（沿用 GenerationRecorder 的既有模式）。
- 删 `runner.py` 手动 per-node call_log 写入（修双写）；删 `persist.py`（provider 不再单独
  落 node_runs，graph_runs 仍由 provider 落 / runner 落）。
- → call_logs 树长成 `根 trace → 节点 span → LLM generation`，节点级 token/cost 靠现成
  `aggregate_rollups` 白送。

### P2 根行补 model + cost
- `aggregate_generation_usage`（api_key.service）扩成同时回填 cost（子行 SUM）+ model_code
  （单模型取之 / 多模型标 `multi`）。agent.service 根行落库时用上。

### P3 删 graph_node_runs
- 删 ORM `GraphNodeRun` + alembic drop 表 + schemas/service/runner/persist 引用。
- 编辑器「日志」详情：listRuns 仍列 graph_runs（运行头），点开走 call_logs trace 树端点
  渲染节点 + LLM 调用 + model/token/cost。
- 测试随之更新（test_graph_* 里断言 node_runs 的改断言 call_logs span）。

### P4 前端观测域拆两 tab（LangSmith 式）
- 「运行记录」= call_logs 根列表 → 点开甘特瀑布（已有，接通后自动显示节点层级）。
- 「会话」= sessions 表列表 → 对话回放 + 每轮直链 trace。
- 顺带验证「会话历史只有一个」根因（sessions 落库 or 跨 origin device_id 隔离）。

### P5 验证
- 浏览器跑 graph 对话 → trace 树展开见节点层级 + 每个 LLM 调用 model/token/cost，根行
  不再「—」。
- human-input pause/resume 不回归。
- pytest graph 套件绿。

## 风险

- core 层 lazy import system.record_call —— 沿用既有 GenerationRecorder 模式，可接受。
- graph_node_runs 删除波及多个 test_graph_* —— P3 一并改断言。
- 双写 bug 修复后，历史 admin-run 的旧数据里 generation 可能仍是双份（不回溯清洗，只保证
  新数据正确）。

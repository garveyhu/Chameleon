# 流式 AI 扩样 + 评审（AI Generate Studio）— SSOT

用户反馈（#221）：数据集 AI 扩样应当
1. 新增组件**实时流式**显示 AI 扩样内容过程；
2. 生成后**动态选择**哪些候选进入样本；
3. 每条候选可**手动编辑 / AI 优化 / 重新生成（单条）**。

对标 Dify「数据集 · AI 生成」与 Braintrust dataset 评审：**生成与入库解耦**——先流式生成候选到评审区，用户挑拣/编辑/优化后再确认导入。

## 现状（被替换）

- 后端 `datasets/ai_generate.py::ai_generate_items`：阻塞 `get_llm(None).ainvoke` → `_parse_generated` → **直接 `bulk_import_items` 全量入库**。端点 `POST /{id}/ai-generate`。
- 前端 `ai-generate-modal.tsx`：任务描述 + 数量 → 阻塞 POST → 全量入库。触发于 `dataset-detail-page.tsx:378`。
- 无流式、无预览选择、无单条编辑。候选形态 `{user_input, answer}`。

## 复用基建

- 后端 SSE：`core/api/sse.py::sse_response(AsyncIterator[dict])` —— 业务产 `dict` 流，自动包 `data:{json}\n\n` + `[DONE]` + 异常兜底 chunk。参照 `graphs/api.py::chat_stream` 端点写法、`playground/service.py::_stream_llm` 的 `async for chunk in bound.astream(messages): yield ...`。
- 前端 SSE：`core/lib/sse.ts::streamSSE<T>(url, {body, signal, onChunk})` —— fetch+reader 解析、token 自动挂、`[DONE]` 自然结束。
- 落库：复用现有 `datasetApi.bulkImport(id, {items, pii_strategy})` → `POST /{id}/items/bulk-import` → `bulk_import_items`。**导入选中无需新端点**。

## 前后端契约（钉死，前后端并行实现按此）

### SSE 流式扩样

`POST /v1/admin/datasets/{dataset_id}/ai-generate/stream`，body `{task_description: str, count: int(1..50)}`，返回 `text/event-stream`。chunk（`{type, data}`）：

- `{"type":"delta","data":{"text":"<增量原文>"}}` —— LLM 流式吐字，前端实时显示「AI 正在生成…」原文。
- `{"type":"candidate","data":{"user_input":"<问题>","answer":"<理想回答>"}}` —— 每解析出一条完整候选推一条（前端落候选卡片）。
- `{"type":"done","data":{"count":<n>}}` —— 收尾。
- 异常由 sse_response 兜成 `{"error":{type,message}}` + `[DONE]`。
- **不落库**（评审优先）。LLM 走 `channel=eval`（成本/token 进 Trace，沿用现有 TraceContext）。

### 单条 AI 优化 / 重新生成

`POST /v1/admin/datasets/{dataset_id}/ai-generate/refine`，body
`{task_description: str, candidate: {user_input, answer}, instruction?: str, mode: "optimize"|"regenerate"}`，
返回 `Result[{user_input, answer}]`。
- `optimize`：在原候选基础上按 `instruction`（可空，默认"提升质量/更清晰严谨"）改写。
- `regenerate`：按 task_description 另起一条同主题但不同的候选（可参考原候选去重）。
- 非流式（单条快）。走 `channel=eval`。

### 导入选中（复用）

前端把选中候选构造为 `BulkImportItem[]`：
`{input_payload:{user_input}, expected_output:{answer}|null, meta:{source:"ai_generate"}}`，
调 `datasetApi.bulkImport(id, {items, pii_strategy:"keep"})`。

## 后端实现（ai_generate.py + api.py + schemas.py）

1. `ai_generate.py`：
   - 新 `async def ai_generate_stream(session, dataset_id, *, task_description, count) -> AsyncIterator[dict]`：载 5 种子 + 设 eval TraceContext + `async for chunk in get_llm(None).astream([HumanMessage(prompt)])` 累计文本并 `yield {"type":"delta",...}`；流末 `_parse_generated(full)` 逐条 `yield {"type":"candidate",...}`；末 `yield {"type":"done",...}`。**不写库**。
   - 新 `async def refine_candidate(*, task_description, candidate, instruction, mode) -> dict`：单次 `ainvoke`，prompt 按 mode 拼，eval TraceContext，返 `{user_input, answer}`（容错解析，失败回原候选）。
   - **删** `ai_generate_items`（被流式+导入替代）。若有测试引用，改测试指向新流程。
2. `api.py`：
   - 新 `POST /{id}/ai-generate/stream` → `return sse_response(ds_ai_generate.ai_generate_stream(session, id, ...), log_label="datasets:ai-generate-stream")`。handler 零业务。
   - 新 `POST /{id}/ai-generate/refine` → `Result.ok(await ds_ai_generate.refine_candidate(...))`。
   - **删**旧 `POST /{id}/ai-generate` + `AiGenerateResult`（或保留 schema 若它处用）。
3. `schemas.py`：新 `AiGenStreamRequest`、`RefineCandidateRequest`、`RefinedCandidate`（candidate 内联 `{user_input:str, answer:str|None}`）。删 `AiGenerateResult`（若仅扩样用）。
4. MVC 铁律：api 只 sse_response/调 service/包 Result，编排全在 ai_generate.py（[[feedback-api-no-logic]]）。

## 前端实现

1. `types/dataset.ts`：`AiGenCandidate{cid:string(本地), user_input, answer, selected, editing?}`、`AiGenStreamChunk{type:'delta'|'candidate'|'done'|'error', data}`、`RefineCandidateRequest`。删 `AiGenerateRequest/Result`（或留 type 若复用）。
2. `services/dataset.ts`：`aiGenerateStream(id, body, {signal, onChunk})` 包 `streamSSE`；`refineCandidate(id, req)` → post。删 `aiGenerate`。
3. 新 `components/ai-generate-studio.tsx`（替 ai-generate-modal）—— 大号 Modal/Drawer 三态：
   - **表单态**：任务描述 + 数量 + 「生成」。
   - **流式态**：实时原文滚动区（typing 感）+ 候选卡片随 `candidate` chunk 逐个浮现；可中断（AbortController）。
   - **评审态**：候选卡片列表，每卡：勾选框 / user_input+answer 行内编辑（textarea）/「AI 优化」（refine optimize）/「重新生成」（refine regenerate，单条原地替换）/「删除」。顶部：全选 + 已选计数 + 「重新全部生成」。底部：「导入选中(N)」→ bulkImport → toast + onDone + 关闭。
   - 本地候选 cid 用 index/计数派生（不可 Math.random，渲染顺序稳定即可）。乐观编辑直接改本地 state。
4. `dataset-detail-page.tsx`：`AiGenerateModal` → `AiGenerateStudio`，触发按钮（:378 Sparkles「AI 扩样」）与 open state 复用。
5. 规范：@ 别名 / 不用 React.FC / Tailwind 主题色 / 强类型 / HTTP 仅在 service（streamSSE 经 service 包装）/ react-hooks 不 disable。

## 验证

- 后端：ruff + import-linter(2 kept) + 建 app；写一次性 pytest 断言 `ai_generate_stream` 产 delta+candidate+done、`refine_candidate` 返 `{user_input,answer}`（跑完删）。
- 前端：tsc(0) + eslint(0)。
- e2e：重启 7009 → 浏览器对真实数据集跑流式扩样 → 看实时流 → 取消选中几条 + 编辑一条 + AI 优化一条 + 重新生成一条 → 导入选中 → 校 DB 新 items 数与选中数一致、内容含编辑/优化结果。
- 提交：单 commit `feat(eval): 流式 AI 扩样 + 候选评审`。

## 风险

- astream 在某些 provider 不吐 usage——token rollup 不受影响（GenerationRecorder 在 ainvoke/astream 都记一行；eval 渠道）。
- 流式端点 session 生命周期：只在流启动时读种子，发流期间不再用 session 写（参照 graphs chat_stream 注释）。
- `_parse_generated` 依赖 LLM 输出完整 JSON 数组——流式期间无法逐条 parse（JSON 未闭合），故 candidate 在**流末**统一 parse 后逐条推；delta 期间只显示原文。这是有意取舍（可读性优先，候选准确性优先），不做不可靠的增量 JSON 解析。

# 评测域后续增强 — 实现设计蓝图

> Workflow w0x8tzw9q 产出（7 领域并行设计 + 完整性 critic，842k tokens）。
> 配套主计划 docs/plans/2026-06-04-eval-domain-refactor.md。这份是各「后续期增强」的落地蓝图。

## judge-contract-multimode　effort=M　依赖=['dsl-parser']

**现状**：judges.py 仅 3 函数（backend/chameleon-system/src/chameleon/system/datasets/judges.py:33-58）：exact_match/contains 二值、llm_judge 死返 0.5（已被 runner 旁路救活）。契约是裸 `async def judge(expected, actual) -> float | None`，单字段、无参、无理由。JUDGES dict（:54）+ list_judges()（:61）是注入与端点数据源。

runner.py 已部分超前于契约：run_dataset（:45-236）里 `if judge=="llm_judge"` 走 `_llm_judge_score`（:267-298，真 AI 评分 0-1+reason，已在 channel='eval' 的 set_trace_context scope 内，:113-121），else 走 `score=await judge_fn(item.expected_output, actual)`（:139）。`_parse_judge_json`（:301-321）、`_flatten_str`（judges.py:18）已可复用。DatasetRunItem 落 score/score_reason（:158-166），但 field_scores/reference_output 字段已迁移却未被 runner 写入。

DatasetRunItem ORM（backend/chameleon-data/src/chameleon/data/models/dataset.py:106-142）：score_reason/field_scores/reference_output 三列已由迁移 p26_g01 铺好（nullable）。DatasetItem（:45-63）有 input_payload/expected_output/meta，无 reference_output 列。EvalTemplate（eval_template.py:26-50）有 config 出口语义（注释允许 customize 走 config，但实际无 config 列，只有 metrics/judge_provider/version）。

schemas：DatasetRunRequest（schemas.py:139-149）有 judge 字段无 judge_config；DatasetRunItemRow/Detail（:152-178）已含 score_reason/field_scores/reference_output（前端已对齐 types/dataset.ts:103）；OptimizeResult（:126-133）独立无关。

两个 run_dataset 调用方：datasets/api.py:239（直接 /run 端点）+ eval_jobs/service.py:209（周期任务，:108/:152 用 `judge not in JUDGES` 校验，:322 _validate_judge）。前端 JUDGE_META（eval-job-form-modal.tsx:44-58，含 exact_match/contains/llm_judge 中文名+说明）+ judges 下拉（:145 拉 /v1/admin/datasets/judges）。

migration heads：p23_w51_channel_keys + p27_a01_model_upstream_fields（newapi 并行，禁碰）。Channel.EVAL 已登记（data/constants/channels.py）。

**方案**：分三层一次性收口契约，新模式挂同一基座；DSL 仅预留接口（dsl-parser 领域单列）。

【① JudgeResult 契约（judges.py 顶部新增 Pydantic/dataclass）】
定义 `JudgeResult{score: float|None, scale: Literal['0-1','1-5']='0-1', reason: str|None=None, field_scores: dict[str,float]|None=None}`。约束：score 始终内部存 [0,1]（D3 决策：UI 层映射 1-5，不污染 mean_score/RAGAS）；scale 仅作 UI 展示提示标记，1-5 模式的 judge 内部把 1-5 归一为 (n-1)/4 落 score，原始档位放 field_scores 或 reason。
向后兼容：保留 exact_match/contains 原签名不变（仍返 float|None），在 runner 调用处统一用 `_as_judge_result(raw)` 适配器包成 JudgeResult（raw 是 float → JudgeResult(score=raw)；raw 是 JudgeResult → 透传；None → JudgeResult(score=None)）。这样旧三函数零改动，新 judge 直接返 JudgeResult。

【② judge_fn 签名升级】
新契约 `async def judge(expected, actual, *, reference=None, config=None) -> JudgeResult | None`。仅新 judge（llm_score/gsb）用这个全签名；旧三函数保持窄签名，靠适配器分发。JUDGES dict 值类型放宽为 Union（保留旧 Callable + 新签名）。新增内部分发器 `async def run_judge(judge_key, expected, actual, *, reference, config, model_override) -> JudgeResult`：按 key 路由——exact_match/contains 调旧函数+适配；llm_judge/llm_score/gsb 是「需 LLM」的 judge，不在 judges.py 直接调 LLM（否则 judges.py 反依赖 integrations，破坏分层），而是把 LLM 评分逻辑留在 runner.py（已有 _llm_judge_score 模式），judges.py 只暴露 prompt 构造 + 解析（纯函数，无 LLM 依赖）。

具体拆分（守 core←data←integrations←engine + judges 纯函数）：
- judges.py（纯逻辑层）：新增 `build_llm_score_prompt(expected, actual, criteria) -> str`、`build_gsb_prompt(reference, actual, criteria) -> str`、`parse_score_result(raw, scale) -> JudgeResult`（吸收现 runner._parse_judge_json，支持 1-5 解析 + gsb 三态 G/S/B→{1.0,0.5,0.0}）。判定哪些 judge 需 LLM：`LLM_JUDGES = {'llm_judge','llm_score','gsb'}`。
- runner.py（编排层，已可依赖 integrations）：`_llm_judge_score` 泛化为 `_run_llm_judge(judge_key, expected, actual, *, reference, config, model_override) -> JudgeResult`，内部 build prompt（调 judges 纯函数）→ get_llm(model_override).ainvoke → parse_score_result。仍在外层 channel='eval' TraceContext scope 内（:113-121 已铺）。

【③ 新增 judge 类型】
- `llm_score`：config={'criteria': str}（用户写多行评分细则）。prompt 让 LLM 按 criteria 输出 1-5 整数档 + reason，parse 归一到 [0,1] 落 score、原档位入 field_scores={'raw_1_5': n}、scale='1-5'。expected 可空（纯按 criteria 评，不依赖金标准）。
- `gsb`：参照源 = reference（来自 DatasetItem.reference_output，见 migration）。prompt 让 LLM 判 actual 相对 reference 是 Good/Same/Bad，落 score∈{1.0,0.5,0.0}、reason 说明、field_scores={'verdict':'G|S|B'}。reference 缺失则返 JudgeResult(score=None)（无参照不可评）。
- `dsl`：本领域【只预留 key + 透传】——JUDGES 登记 'dsl'，run_judge 收到 dsl 时 try import `chameleon.system.datasets.dsl.evaluate`（dsl-parser 领域产出），未实现则返 JudgeResult(score=None, reason='DSL 解析器待接入')。config 透传 {'dsl': str}。不在本领域写解析逻辑。
- exact_match/contains/llm_judge 保留（llm_judge 即 llm_score 无 criteria 的退化，可让 JUDGE_META 标注「AI 评分(基础)」）。

【④ DatasetRunRequest.judge_config】
schemas.py:DatasetRunRequest 加 `judge_config: dict[str, Any] | None = None`（承载 criteria/dsl 文本/gsb 参照源开关）。run_dataset 加同名形参透传。eval_jobs 侧同步：EvalJobRunConfig/Trigger schema 加 judge_config（eval_jobs/schemas.py），EvalJob 模型加 `judge_config` JSON 列（与 dataset run 一致），eval_jobs/service.py:209 透传。_validate_judge（eval_jobs/service.py:322）+ datasets run_dataset 的 `judge not in JUDGES` 校验（runner.py:57）随 JUDGES 扩容自动放行新 key。

【⑤ runner.py 适配新契约 + 落库】
重写 :133-166 评分段：统一 `result = await run_judge(judge, item.expected_output, actual, reference=item.reference_output, config=judge_config, model_override=model_override)`（reference 取 DatasetItem 新列）；落库 `DatasetRunItem(..., score=result.score, score_reason=result.reason, field_scores=result.field_scores, reference_output=item.reference_output if judge=='gsb' else None)`。mean_score/Score 表回写（:170-185）不变（仍用 [0,1] score）。run.summary 可选加 judge_scale 标记供前端映射。

【前端（本领域只动 judge 选择面板 + 透传，电子表格/GSB 人工判 UI 属模块 E/H 后续）】
- eval-job-form-modal.tsx：JUDGE_META 扩 llm_score（'AI 评分(自定义标准)'）/gsb（'GSB 对比(无金标准)'）；judge 选中 llm_score/gsb 时条件渲染 criteria 多行 textarea / 参照源说明，组装成 judge_config 随 create payload 透传。
- 数据集 /run 触发处（dataset-detail-page run 入口）同步加 judge_config 透传 + types/dataset.ts:DatasetRunRequest 加 judge_config 字段。
- services 走 datasets/services/dataset.ts，HTTP 不出 service 层。

数据流：UI judge+judge_config → run_dataset(judge, judge_config) → run_judge 分发 → (LLM judge 在 eval TraceContext scope 调 get_llm，channel='eval' 自动盖章，不新增切面) → JudgeResult → DatasetRunItem 落 score/reason/field_scores/reference_output → list_run_items 已带回（service.py:525 model_validate 自动含三列）。

**文件**：backend/chameleon-system/src/chameleon/system/datasets/judges.py, backend/chameleon-system/src/chameleon/system/datasets/runner.py, backend/chameleon-system/src/chameleon/system/datasets/schemas.py, backend/chameleon-data/src/chameleon/data/models/dataset.py, backend/chameleon-data/src/chameleon/data/models/eval_job.py, backend/chameleon-system/src/chameleon/system/eval_jobs/schemas.py, backend/chameleon-system/src/chameleon/system/eval_jobs/service.py, backend/chameleon-system/src/chameleon/system/datasets/api.py, backend/migrations/versions/p27_g02_dataset_item_reference_judge_config.py, frontend/src/system/eval_jobs/components/eval-job-form-modal.tsx, frontend/src/system/datasets/types/dataset.ts, frontend/src/system/datasets/services/dataset.ts, frontend/src/system/datasets/pages/dataset-detail-page.tsx

**迁移**：需要一支新 alembic（不碰已发布 p26_g01，也不碰 newapi 的 p27_a01）。revision=p27_g02_dataset_item_reference_judge_config，down_revision=p26_g01_run_item_judge_fields（挂在评测链尾，与 newapi 的 p27_a01 形成两 head——本来就是两 head 并存，最终 merge 由别人收）。加列：
1) dataset_items.reference_output JSON nullable（D5 决策：GSB 参照，区别 expected_output 金标准语义，加列不改列）。
2) eval_jobs.judge_config JSON nullable（周期任务承载 criteria/dsl 文本）。
DatasetRun 本身【不】需要 judge_config 列——run 是即时执行，judge_config 仅请求期透传给 runner，不必持久化到 dataset_runs（如需复跑审计可后续再评估，本期不加）。三个 run_item 列（score_reason/field_scores/reference_output）p26_g01 已铺，无需再加。SQLite 用 op.add_column 加 nullable 列安全（非改/删，无需 batch_alter_table）。每列写 --rollback 对应 drop_column。

**风险**：judges.py 若直接 import integrations.llms.factory 会破坏 core←data←integrations←engine 单向契约（judges 在 system 层但作为纯逻辑应无 LLM 依赖）——设计已规避：LLM 评分留在 runner.py（编排层可依赖 integrations），judges.py 只出 prompt 构造 + 解析纯函数。落地时务必让 import-linter 两契约保持 GREEN。；JUDGES dict 值类型从窄 Callable 放宽为 Union 后，list_judges()/api 端点/eval_jobs._validate_judge 三处的 `judge in JUDGES` 校验仍成立，但需确认前端 JUDGE_META 同步登记新 key，否则下拉显示原始英文 key。；1-5 与 [0,1] 双量纲：必须严守 D3——score 永远落归一 [0,1]，1-5 原档只进 field_scores/reason，否则 mean_score/RAGAS/score_distribution 桶（service.py:_bucketize 假定 [0,1]）全错。；gsb reference 缺失返 score=None 会让该 item 不计入 mean_score（runner.py:170 `if score is not None`），需在 UI/summary 明确「无参照样本已跳过」避免误读通过率。；eval_jobs 加 judge_config 列触发新迁移 + EvalJob/schema 改动，与 newapi 的 p27_a01 同为 p27 双 head；务必确认 down_revision 挂 p26_g01 而非 p27_a01，绝不依赖 newapi 字段。；DatasetRunRequest 加 judge_config 后，前端 run 触发若不传则为 None，run_judge 对 llm_score/gsb 缺 config 要优雅降级（llm_score 无 criteria 退化为 llm_judge 语义；gsb 无 reference 返 None），不能抛异常中断整 run。

**分期建议**：本期做契约升级 + llm_score + gsb（D4/D6 决策第 2 期：先 llm_score 1-5+reason 救活、再 GSB）。dsl judge 本领域【只预留 key + try-import 透传桩】，真解析器是 dsl-parser 领域、按 D4 第 3 期后置——理由：DSL 文本解析器是独立复杂子系统（语法/聚合/格式校验/规则块），第 2 期先用「可视化逐字段配置」覆盖多数场景（D4 明确），DSL 文本作高级出口后置。judge_config 的 dsl 字段本期就预埋（schema + 透传链通），第 3 期 dsl.evaluate 落地即插即用，不返工。GSB 的人工判 UI（左右回答 + G/S/B 按钮）属模块 E run-detail 三栏视图，本领域只保证 AI 自动判 gsb + 后端落 verdict，人工判后续期。

---

## eval-judge-config-frontend　effort=M　依赖=['judge-contract-backend']

**现状**：judge 配置当前是一个裸 Radix Select，散落在两个地方，无配置面板。

**主要锚点：eval-job-form-modal.tsx**（`frontend/src/system/eval_jobs/components/eval-job-form-modal.tsx`）
- `JUDGE_META`（:45-58）已建好 3 个评分方式的中文 label + desc（exact_match/contains/llm_judge），但只覆盖已有 3 种，缺 GSB/DSL。
- judge state 是单字段 `const [judge, setJudge] = useState(...)`（:104），无 judge_config 容器。
- 评分方式 UI 是 `<Select value={judge} onValueChange={setJudge}>`（:278-289）+ 一段 desc 文案（:290-294），数据源 `judgesQ`（:145-150，`GET /v1/admin/datasets/judges` 返 `string[]`）。
- payload 构造（:184/:199）只透 `judge` 字符串，无 judge_config。
- 父层 remount key 已就位：`eval-job-detail-page.tsx:184 key={job?.id ?? 'edit'}`、`eval-jobs-page.tsx:341`。惰性 useState 模式全程遵守（:85 注释）。

**次要锚点：eval-template-form-modal.tsx**（RAGAS 加权多 metric，独立体系，**不在本次升级范围**）——它走 `algorithm`/`weight`/`threshold`（:33-41 ALGO_OPTIONS），是 template_scoring.py 红线 RAGAS 路径，与 judge 多模式是两套并行体系，设计上不要混。

**类型层**
- `eval-job.ts`（`frontend/src/system/eval_jobs/types/eval-job.ts`）：`CreateEvalJobPayload`/`UpdateEvalJobPayload`/`EvalJobItem` 都只有 `judge: string`（:22/:40/:53），无 judge_config。
- `dataset.ts`（`frontend/src/system/datasets/types/dataset.ts`）：`DatasetRunItemRow` 已有 `score_reason?`（:104），后端 schemas.py:160-163 已扩 `score_reason/field_scores/reference_output`（迁移 p26_g01 已落库）。

**已有可复用基础**
- `core/components/ui/json-editor.tsx`：CodeMirror 6 封装（已落地，B 模块），`value/onChange/readOnly/label/wrap`，自带格式化 + 实时 JSON 语法校验 + 错误条。DSL 文本编辑直接复用。
- `core/components/common/model-picker.tsx`：chat 模型选择器（:33），GSB「AI 自动判用哪个模型」/ AI 评分模型槽直接复用。
- `core/components/ui/{select,input,label,button,modal}.tsx`、`cn`（`core/lib/cn`）。
- 后端契约耦合点：`runner.py:run_dataset`（judge 字符串 + JUDGES dict，:57 校验、:102 注入、:133-139 llm_judge 已救活带 reason）；`DatasetRunRequest.judge`（schemas.py:145）；`eval_jobs/service.py:_validate_judge`（:322）。**当前 judge 是 `str`，无 judge_config 字段** —— 这是与 judge-contract-backend 的核心耦合点。

**方案**：## 一、整体策略：抽出共享「评分配置」子组件，两表单复用

judge 配置目前只活在 eval-job-form-modal，但 G 模块后续 dataset-run 触发对话框也要用同一套。所以**不在 modal 内联堆 UI**，而是新建一个自包含子组件 `JudgeConfigPanel`，输入 `{ judge, judgeConfig }`、输出 `onChange(judge, judgeConfig)`，两处（eval-job、未来 dataset-run dialog）复用。单一职责：只管「选模式 + 配该模式参数」。

## 二、judge_config 数据形状（前端契约，与后端对齐）

定义在 `system/datasets/types/judge.ts`（新建，放 datasets 域因 judge 是 dataset 评测概念，eval-job 只是引用方）：

```ts
export type JudgeMode =
  | 'exact_match' | 'contains'   // 二值，无配置
  | 'llm_judge'                  // AI 评分(1-5+理由)
  | 'gsb'                        // GSB 对比
  | 'dsl';                       // 多字段

export interface LlmJudgeConfig { criteria?: string; model?: string }
export interface GsbConfig { reference_source: 'reference_output' | 'expected_output'; model?: string }
// DSL：D4 第2期先可视化「字段→函数+聚合」，DSL 文本是第3期高级出口
export interface DslFieldRule {
  field: string;
  fn: 'exact' | 'fuzzy' | 'length' | 'format' | 'const_eq' | 'nl_rule';
  param?: string;               // 函数参数（如格式=json/字数=50/自然语言规则文本）
}
export interface DslConfig {
  aggregate: 'min' | 'max' | 'mean' | 'median' | 'mode';
  rules: DslFieldRule[];
  raw?: string;                 // 第3期 DSL 文本出口；存在时以文本为准
}
export type JudgeConfig =
  | LlmJudgeConfig | GsbConfig | DslConfig | Record<string, never>;
```

`judge_config` 整体作为一个 `Record<string,unknown> | null` 透传到后端（避免前端 union 强耦合后端枚举演进）。前端只负责构造正确形状，后端按 `judge` 字段分派解析。

## 三、① 模式卡片（替代 Radix Select）

`JudgeConfigPanel` 顶部渲染一组卡片（`role="radiogroup"`，每卡 `role="radio"` + `aria-checked`），网格 `grid grid-cols-2 gap-2`（或 5 个用 `grid-cols-1 sm:grid-cols-2`）。每卡：模式中文名（来自升级后的 `JUDGE_META`）+ 一行说明 desc + 选中态。

- `JUDGE_META` 从 eval-job-form-modal 提升到 `types/judge.ts` 导出（消除 eval-job 域对 judge 文案的私有持有），补齐 5 项：精确匹配 / 包含匹配 / AI 评分(1-5+理由) / GSB 对比 / DSL 多字段。
- 选中态：Tailwind 主题色，`border-primary-500 ring-1 ring-primary-200 bg-primary-50/40`（不硬编码 hex，沿用 modal 内既有 `primary-*` token）；未选 `border-stone-200 hover:border-stone-300`。
- 可用模式来源：`judgesQ`（`GET /v1/admin/datasets/judges`）返回的 key 集合决定哪些卡可点；后端未注册的模式卡置灰 disabled（向后兼容——GSB/DSL 后端就绪前自动隐藏/置灰，前端不写死可用集）。
- 卡片本身**不是 HTTP 调用方**，可用列表由父 modal 的 query 传入 `availableModes: string[]` prop（遵守 HTTP 只在 services/）。

## 四、② 各模式配置面板（卡片下方条件渲染）

选中卡下方一个 `rounded-md border bg-stone-50/40 p-3` 配置区，按 `judge` 切：

- **exact_match / contains**：无面板，仅一行 desc 提示「无需额外配置」。
- **llm_judge（AI 评分 1-5+理由）**：
  - `criteria` 多行 `<textarea rows={4}>`（复用 modal 内既有 textarea 样式，:357 那套 className），placeholder「逐行写评分细则，如：1. 是否覆盖所有要点 2. 语气是否专业…」。
  - 评判模型槽：复用 `ModelPicker`（`value=config.model`，`placeholder="不指定·用系统默认 chat 模型"`，对齐 D6）。
  - 量纲提示文案：「内部 0–1 存储，结果以 1–5 展示」（对齐 D3，**不在前端做换算，只展示提示**）。
- **GSB 对比**：
  - 参照回答来源 `<Select>`：`reference_output`（独立 GSB 参照字段，对齐 D5）/ `expected_output`（复用金标准）二选一，带说明「GSB 比较模型回答与参照回答的相对优劣（G 胜 / S 平 / B 负）」。
  - 评判模型槽：`ModelPicker`（AI 自动判 GSB 用）。
- **DSL 多字段**（D4：可视化先）：
  - 「字段→函数+聚合」可视化构建器，复用 eval-template-form-modal 的**行式编辑范式**（:211-272 的 `grid + 加行/删行 + patchRow`，照抄结构，不照抄 RAGAS 语义）：每行 = 字段名 `<Input>` + 函数 `<Select>`（精确/模糊(1-5)/字数限制/格式限制/常量等于/自然语言规则）+ 参数 `<Input>`（函数依赖时露出）+ 删除按钮。
  - 顶部聚合方式 `<Select>`（min/max/mean(默认)/median/mode）。
  - 第3期 DSL 文本高级出口：一个「切到文本模式」开关 → 露出 `JsonEditor`-style 的 CodeMirror（用纯文本 lang，非 json），承载 DSL 原文（`config.raw`）。**本期不做文本模式**（见 phase_advice），只留 union 字段位。

## 五、③ judge_config 透传链路

三条落点，**都从单一 `JudgeConfigPanel.onChange` 出发**：

1. **eval-job**：`eval-job-form-modal.tsx` 把 `judge` 单 state 升级为 `{ judge, judgeConfig }`（仍惰性 useState：`const [judgeConfig, setJudgeConfig] = useState(() => initial?.judge_config ?? {})`，父层 `key={job?.id}` remount 保证编辑回填）。payload（:184/:199）追加 `judge_config: Object.keys(jc).length ? jc : null`。
   - 类型层 `eval-job.ts`：`CreateEvalJobPayload`/`UpdateEvalJobPayload`/`EvalJobItem` 加 `judge_config?: Record<string,unknown> | null`。
2. **dataset-run**（G 模块新触发对话框，本期可不建，但类型先留位）：`dataset.ts` 若后续加 `runDataset` service，`DatasetRunRequest` 类型加 `judge_config`。
3. **eval-template**：**不接** judge_config —— template 是 RAGAS 加权独立体系，与 judge 多模式正交，强行合并会破坏 D3 量纲与 template_scoring 红线。设计上明确划清。

## 六、④ 复用清单

| 需求 | 复用 | 方式 |
|------|------|------|
| 模式卡片选中态 | Tailwind `primary-*` token + `cn` | 不新建组件库，纯 div+role |
| AI 评分/GSB 模型槽 | `core/components/common/model-picker.tsx` | 直接 `<ModelPicker>` |
| DSL 可视化行编辑 | `eval-template-form-modal.tsx` 行式范式（:97-100 patchRow/removeRow，:211-272 grid） | 照抄交互结构 |
| DSL 文本出口（第3期） | `core/components/ui/json-editor.tsx` CodeMirror 思路 | 换纯文本 lang 扩展 |
| criteria 多行 | modal 内既有 textarea className（:357） | 复用样式 |
| 可用模式列表 | `judgesQ`（`/v1/admin/datasets/judges`） | 父 modal query → prop 注入 |

## 七、与 judge-contract-backend 的耦合点（关键）

1. **新增 `judge_config` 字段贯穿后端三处**（前端依赖它存在）：`DatasetRunRequest`（schemas.py:139）、`eval_jobs` 的 Create/Update schema（schemas.py:25/44/57）、`EvalJob` 模型列。**后端不就位前，前端 judge_config 透了也被忽略，不会破坏现状**（向后兼容）。
2. **`/v1/admin/datasets/judges` 返回形状是否升级**：当前返 `string[]`。前端卡片只需 key 集合，`JUDGE_META` 文案在前端持有即可——**建议端点保持 `string[]`**（前端控文案，符合 i18n 归前端），后端只管「哪些 judge 注册了」。若 backend 倾向返 `[{key,label,desc}]`，前端能吃但非必需；两边定一个即可。
3. **GSB 的 `reference_output` 落点**：前端 `GsbConfig.reference_source` 选 `reference_output` 时，依赖 `DatasetItem.reference_output` 列存在（D5，迁移 p26_g01 已在 DatasetRunItem 加，DatasetItem 侧需 backend 确认）。前端 GSB 面板的「参照来源」选项可用性应跟随后端能力。
4. **DSL 函数枚举**：前端可视化构建器的函数集（精确/模糊/字数/格式/常量/自然语言规则）必须与 backend `dsl.py` 内置函数名一一对齐 —— **这是强契约耦合，需 judge-contract-backend 先定函数名常量集，前端 import 对齐或共识一份常量**。建议后端出一个 `GET /v1/admin/datasets/judge-meta` 返各模式可配字段 schema + DSL 函数清单，前端据此渲染（避免前端硬编码后端枚举）。本期若 DSL 后端未就绪，前端 DSL 卡置灰。

**文件**：frontend/src/system/datasets/types/judge.ts (新建：JudgeMode/JudgeConfig/JUDGE_META 提升至此), frontend/src/system/datasets/components/judge-config-panel.tsx (新建：模式卡片 + 各模式配置面板，自包含子组件), frontend/src/system/eval_jobs/components/eval-job-form-modal.tsx (judge Select → JudgeConfigPanel；judge_config state + 透传), frontend/src/system/eval_jobs/types/eval-job.ts (Create/Update/Item 加 judge_config?), frontend/src/system/datasets/types/dataset.ts (DatasetRunRequest 类型若新建则加 judge_config，留位)

**迁移**：无（纯前端 + 透传字段）。judge_config 落库的迁移属于 judge-contract-backend 领域（EvalJob 加 judge_config 列、DatasetRunItem 的 reference_output 已在 p26_g01）。前端不发起迁移。

**风险**：DSL 可视化构建器的函数集若前端硬编码、与 backend dsl.py 内置函数名漂移，会出现配了跑不通的静默失败——必须靠后端 judge-meta 端点或共享常量集对齐（强契约耦合）；judge_config 是自由 dict 透传，前端 union 类型只在构造侧约束，后端解析侧若 schema 校验严格会 422——需 backend 对未知/缺失字段宽容（向后兼容）；GSB 的 reference_output 在 DatasetItem 侧是否已有列需 backend 确认；前端选了 reference 来源但库里无该字段会全 None；eval-template-form-modal 与 judge 多模式是两套并行体系，若误把 judge_config 塞进 template 会破坏 D3 量纲/RAGAS 红线——设计已划清，实现时勿混；judges 端点当前返 string[]，若 backend 改返对象前端要同步；建议锁定 string[] + 文案归前端，避免双改

**分期建议**：本期（第2期 P1）做：① 模式卡片化 + ② exact/contains/llm_judge(criteria+model) + GSB(参照来源+model) 配置面板 + ③ judge_config 透传到 eval-job。这些只依赖 judge-contract-backend 把 judge_config 字段铺通（向后兼容，未铺通也不破坏现状）。

DSL 模式按 D4 分两步：本期只做「可视化字段→函数+聚合」构建器（覆盖多数 JSON 逐字段场景），**DSL 文本编辑出口后置到第3期**（plan 第3期「G 的 DSL 文本高级出口」）。理由：DSL 文本解析器（backend dsl.py）是 L 工作量、第3期才做，前端文本编辑器无后端解析就是空壳；可视化构建器配的字段函数也需 backend dsl.py 的函数枚举对齐，**若第2期 backend DSL 未就绪，DSL 卡先置灰/隐藏**（前端按 judges 端点可用集自适应，不写死）。

强依赖前置：DSL 函数枚举与 GSB reference 落点必须 judge-contract-backend 先定，建议后端补 `GET judge-meta` 端点供前端渲染，避免前端硬编码后端枚举。

---

## eval-scale-ui-1to5　effort=M　依赖=['eval-judge-multimode']

**现状**：核心展示工具集中在 frontend/src/core/lib/score.ts：formatScore（:24-30，固定 toFixed(2)，入参 number|string）、scoreColor（:4-11，阈值 0.8/0.5）、scoreBg（:14-21）、parseScore（:33-39）。全部对 [0,1] 原始值工作。

调用处（grep 全量）：
- run-detail-drawer.tsx:148/338（明细表分数 chip + ItemDetail 分数 chip，scoreBg+formatScore）；该组件 useQuery 自取 run detail，runQ.data.judge 已可用（:192 已渲染「评分器 {judge}」），:286 直接 metric.mean.toFixed(2) 画直方图均值，:314-317 直方图 X 轴硬写 "0"/"1"，:299 bucket title `[low,high)`，:44-45 bucketColor 阈值 0.5/0.8。
- run-stats-overview.tsx:44/49（最佳/最近平均分卡），:52 delta toFixed(2)，:68-80 TimeSeriesChart 趋势（Y 轴隐含 [0,1]）。
- run-compare-matrix.tsx:133（列头均值）、:183（单元格分数）、:223（选中 cell 分数）；:56-58 win/tie/loss 直接比原始 a/b（与量纲无关，不动）。
- dataset-detail-page.tsx:229（运行表「平均分」列，scoreColor+formatScore），:217 已渲染 r.judge。
- datasets-page.tsx:142（列表 last_run_score，scoreColor）。
- eval-jobs-page.tsx:107（toast mean_score）、:153（last_score 列）。
- eval-job-detail-page.tsx:214（last_score KPI）、:259/329（mean_score 历史趋势+表）、:339（delta）。

类型：DatasetRunRow.judge:string 已在 types/dataset.ts:77 透出到前端（compare/列表/详情均带），eval-job.ts:21/40/53 也带 judge。→ scale 可纯前端从 judge 派生，无需后端新字段。
runner.py:162 score 存原始 [0,1] float；:133-140 llm_judge 已是 0-1 连续分；JUDGE_META（eval-job-form-modal.tsx:45-58）已有中文评分方式名+量纲说明文案。
偏好基建：core/stores/preferences.ts（Zustand+localStorage+data-* DOM 属性，:33-45 UserPreferences），但本设计【不】把 scale 放这里（理由见 design）。

**方案**：目标（D3）：内部 [0,1] 永不变，仅 UI 渲染层把 0.83 显示成 4.2/5。改动严格收敛在 score.ts + 各展示处的「最后一公里格式化」，统计/聚合/导出/RAGAS/mean_score 一律不碰。

① score.ts 扩 scale 形参（不新建 formatScore15，避免双实现分叉）
- 定义类型：`export type ScoreScale = '0-1' | '1-5';`
- formatScore 加可选第二参 `scale: ScoreScale = '0-1'`：
  - '0-1'：维持现状 toFixed(2)（默认值保证所有未传 scale 的旧调用零行为变化）。
  - '1-5'：映射 `1 + clamp(n,0,1)*4` → toFixed(1)，返回纯数字字符串 "4.2"（"/5" 后缀由调用方在 UI 旁标，避免污染纯函数返回值，便于 tnum 对齐/排序场景）。
- 新增轻量纯函数 `toDisplayScale(n: number, scale): number`（给需要画轴/算 delta 的地方复用同一映射，不重复写 `1+x*4`）。
- scoreColor / scoreBg 不加 scale 形参：它们按【原始 [0,1]】阈值着色（0.8/0.5），色带语义与量纲无关；调用方先拿原始值算色、再用 formatScore(_, scale) 出文本。保持单一职责。
- 阈值映射对照（仅文档/tooltip 用）：0.8→4.2、0.5→3.0，色带边界换算成 1-5 标注在直方图轴。

② 量纲开关放哪：判定为「judge.scale 驱动 + 数据集级展示偏好兜底」，【不上全局偏好、不进 preferences store】
- 主驱动：scale 由 judge 类型决定。后端 G 模块 JudgeResult{scale} 落地后，scale 是评分语义的一部分（llm_score/dsl 的 1-5 内置函数天然 1-5；exact/contains/RAGAS 天然 0-1）。前端从 run/job 已有的 `judge` 字段派生 scale：
  - 建 `frontend/src/system/datasets/lib/judge-scale.ts`：`judgeScale(judge: string): ScoreScale`，映射表 { exact_match:'0-1', contains:'0-1', llm_judge:'1-5'(救活后按 1-5 呈现，配 JUDGE_META 文案), llm_score:'1-5', dsl:'1-5', gsb:'gsb'(GSB 走 W/T/L 不走数值，本设计不映射), default:'0-1' }。单一真相源，所有展示处调它。
  - 为什么不靠后端新字段：DatasetRunRow.judge 已全链路透出（types/dataset.ts:77），客户端派生零迁移、零端点改动，且 judge→scale 是稳定一对一。后端 JudgeResult.scale 仍按 G 模块落库（持久化语义需要），但【前端展示不依赖它返回】——若后续后端 run row 也透出 scale 字段，judgeScale 可优先读 row.scale、缺失再按 judge 派生（前向兼容写法预留）。
- 兜底/覆盖：同一 dataset 多 run 可能混用 judge（如先 exact 后 llm_score），混排时各 run 按【自己的 judge】定 scale（run-compare-matrix 列头、dataset-detail 运行表行级各自派生），不取数据集级统一开关——避免「A run 是 0-1、B run 是 1-5 却被强制同尺显示」的错配。数据集级偏好仅作为「列表 last_run_score 这类无 run 上下文场景」的展示提示，可后置。

③ 跟随改动的展示处（按 scale 派生粒度）
- run-detail-drawer：runQ.data.judge → judgeScale 得 scale；:148/:338 formatScore(ri.score, scale) + 旁标 "/5"（仅 1-5 时）；:286 直方图均值、:314-317 X 轴 "0"/"1" 改 "1"/"5"、:299 bucket title 用 toDisplayScale 标 [1.0,1.8) 等；:44-45 bucketColor 仍按原始 low 阈值不动。
- run-stats-overview：组件需新增 `scale` prop（由父 dataset-detail-page 传入；多 judge 混排时该聚合卡按「最近一次 run 的 judge」定 scale，或显式标注尺）；:44/:49/:52 formatScore+delta 用映射，趋势图 Y 轴域 [1,5]。
- run-compare-matrix：列头 :133 / 单元格 :183 / 选中 :223 各按【该列 run 的 judge】派生 scale 独立格式化（runs[i].judge），不强制全表同尺；win/tie/loss（:56-58）不动。
- dataset-detail-page 运行表 :229：render r 内 judgeScale(r.judge) → formatScore(s, scale)。
- datasets-page 列表 :142 / eval-jobs-page :153 / eval-job-detail-page :214/:329：行/卡片有各自 judge（DatasetListRow 需确认是否带 judge；若列表行无 judge 字段，则 last_run_score 这类降级为默认 0-1 显示 + 不强转，避免假 1-5），优先按 judge 派生，缺 judge 退 '0-1'。

④ 保证内部存储/聚合/导出仍 [0,1]
- runner.py:162 落库、mean_score/summary 聚合、score_distribution 端点、RAGAS template_scoring、Excel 导出（C 模块）一律读写原始 [0,1]，本设计完全不 touch 后端任何计算路径。
- 映射只发生在 React render 出文本/画轴的最末端；任何排序（dataset-detail score 列 sortable）、delta 计算、阈值着色都基于原始值，1-5 只是显示皮肤。
- 导出/复制场景若展示 1-5，需在列头标注「(1-5)」并确保导出文件仍写原始值（与 D2 SheetJS 导出对齐：导出走原始，不走 display 字符串）。

需后端配合度：【极低/可选】。展示侧零依赖后端改动即可全量落地（靠前端 judge→scale 派生）。后端 JudgeResult.scale（G 模块）仍要落库做持久化语义真相源，但属 G 模块工作，本领域只在 judgeScale 里预留「优先读 row.scale」的前向兼容分支，不阻塞、不新增端点/迁移。

**文件**：frontend/src/core/lib/score.ts, frontend/src/system/datasets/lib/judge-scale.ts (新建), frontend/src/system/datasets/components/run-detail-drawer.tsx, frontend/src/system/datasets/components/run-stats-overview.tsx, frontend/src/system/datasets/components/run-compare-matrix.tsx, frontend/src/system/datasets/pages/dataset-detail-page.tsx, frontend/src/system/datasets/pages/datasets-page.tsx, frontend/src/system/eval_jobs/pages/eval-jobs-page.tsx, frontend/src/system/eval_jobs/pages/eval-job-detail-page.tsx, frontend/src/system/eval_jobs/components/eval-job-form-modal.tsx (JUDGE_META 量纲文案对齐 1-5)

**迁移**：无（纯前端展示层映射；后端不新增列/字段/迁移）。后端 JudgeResult.scale 的落库属 G 模块迁移，与本领域解耦；本领域不要求它先行。

**风险**：多 judge 混排同一 dataset：若错误地取数据集级统一 scale，会把 0-1 run 显示成假 1-5。必须 run/列/行各自按自身 judge 派生 scale，已在 design ③ 锁定。；scoreColor/scoreBg 阈值（0.8/0.5）是按 [0,1] 写死的；若误把 1-5 值传进着色函数会全红。约束：着色永远传原始值，只有 formatScore 收 scale。；列表行（DatasetListRow/datasets-page last_run_score、eval-jobs-page last_score）可能不带 judge 字段，无法派生 scale → 需确认；缺 judge 时降级 0-1 显示而非假 1-5，否则同一分数列表页 0.83、详情页 4.2 两套数字误导用户。建议列头统一标注量纲。；导出/复制：若 UI 显示 1-5 但导出仍 0-1，用户可能困惑。需列头标注 (1-5) 且导出明确走原始值（与 C/D2 对齐）。；趋势图（run-stats-overview TimeSeriesChart、eval-job-detail mean_score 历史）Y 轴域需随 scale 切 [0,1]/[1,5]，否则 1-5 值在 [0,1] 域里全部顶格——需给 chart 传 domain。

**分期建议**：本期可做 score.ts + judge-scale.ts + 各展示处 formatScore(scale) 接线（纯前端、零后端依赖、零迁移，价值即时）。但「哪些 judge 算 1-5」的权威映射依赖 G 模块新 judge 类型（llm_score/dsl/gsb）落地——故按 D4 节奏：第 1 期可先把基建（score.ts scale 形参 + judgeScale 骨架，仅 exact/contains/llm_judge 三态）落地并让 llm_judge 按 1-5 呈现（与 JUDGE_META 已有文案对齐）；llm_score/dsl/gsb 的 scale 分支随 G 模块多模式 judge（第 2 期）补全。GSB 不走数值映射（W/T/L），归 G 模块 GSB UI，不在本领域。理由：scale 真相源是 judge 语义，judge 多模式不落地则 1-5 映射只是空架子。

---

## H2 评测集电子表格编辑（spreadsheet item editing）　effort=L　依赖=[]

**现状**：items tab 当前是只读 DataTable：dataset-detail-page.tsx:116-177 定义 itemCols（来源/输入 JsonCell/预期输出 JsonCell/采样时间/铅笔图标），dataset-detail-page.tsx:375-383 渲染 DataTable minWidth=680，铅笔点击只 setEditItem 开抽屉。
编辑只走「全字段抽屉」：dataset-item-editor-drawer.tsx（三段 JsonEditor=CodeMirror，input/expected/meta，整对象 JSON 编辑，updateItem 一次提交）。
批量导入：bulk-import-modal.tsx（粘贴 JSONL/JSON 或 SheetJS 解析 Excel→BulkImportItem[]→datasetApi.bulkImport），列模板 dataset-xlsx.ts:9 TEMPLATE_HEADERS=['输入','理想回答','元数据(JSON)']，cellOf/parseCell 已有「单字段对象↔纯文本」互转逻辑（dataset-xlsx.ts:13-47）。
service 端已有可复用基础：update_item（service.py:205-223，按字段非空更新 input_payload/expected_output/meta，【不】重跑 PII）；bulk_import_items（service.py:343-392，逐条 apply_pii_strategy_dict 后入库 + count(*) 重算 item_count）；list_items（service.py:186-202，按 created_at desc，limit 默认 200）。
端点：update_item POST /items/{item_id}/update（api.py:168-176），bulk-import（api.py:193-205）。【缺】单条 create-item 端点 + delete-item 端点。
列推断的数据现实：sampled item 的 input_payload 是脱敏嵌套结构（service.py:_redact_input，每个 key 是 {hash,length,preview} 对象，service.py:413-440）；manual import 的 input_payload 是扁平 {user_input: "文本"} 或用户原始 JSON（dataset-xlsx.ts:90 parseCell wrapKey='user_input'）。两种形态混在同一 dataset 内。
DataTable 不支持编辑态（data-table.tsx 纯展示 render，无 cell-edit/可控聚焦）。前端 model-picker（common/model-picker.tsx）已存在但与本领域无强依赖。item_count 仅在 sample/bulk-import 后 count(*) 重算（service.py:310/323/384），无单条增删的维护路径。

**方案**：【整体定位】electronic spreadsheet = 新建一个「样本电子表格」组件替换 items tab 的只读 DataTable，但与 dataset-item-editor-drawer / bulk-import-modal【并存】（见末段关系判断）。不引入重型表格库（ag-grid/handsontable 体积大、与 DataTable 暖色 token 冲突、违反「复用 DataTable / 禁丑下拉」）；采用【手写 editable table，按 DataTable 视觉规范自建一个轻量 editable variant】。

① 动态列推断（核心）。新建 util `dataset-spreadsheet.ts`，导出 inferColumns(items): {varKeys: string[]}：
  - 扫描全部 items 的 input_payload，并集出所有 top-level key（保持首次出现顺序）= {{var}} 列。
  - 单元格取值复用 dataset-xlsx.ts 思路：对每个 var key 的 value，若是脱敏对象（含 preview 字段）取 preview 只读展示并标灰「采样脱敏」不可编辑；若是字符串/数字直接编辑；若是复杂对象/数组则降级为「点开 JsonEditor 弹层编辑」。这样兼容 sampled（脱敏嵌套，只读）+ manual（扁平文本，可编）两种形态，不强行拍平。
  - 固定尾列：理想回答（expected_output，单字段取文本，多字段降级 JSON 弹层）、meta（标签摘要，点开弹层）、操作（删行）。
  表头：动态 var 列 header 直接用 key 名；理想回答/元数据中文固定列。空 dataset（无 item）时给一列默认占位 + 「新增行」按钮起步。

② 行内编辑（点单元格编辑，失焦保存）。新建组件 `dataset-spreadsheet.tsx` + 私有 EditableCell：
  - 单元格默认渲染纯文本（截断 + title）；点击进入编辑态（受控 local state，惰性 useState 初始化当前值，禁 set-state-in-effect）；失焦(onBlur)或 Enter 提交，Esc 取消还原；编辑态用 Input（core/ui/input.tsx）。
  - 提交时只对「该行该字段」构造 patch：var 列 → input_payload = {...原, [key]: 新值}；理想回答 → expected_output；调 updateItem（逐条，见④）。乐观更新：mutation onMutate 改 query cache 对应行，onError 回滚 + toast。query key ['datasets', dsId, 'items']。
  - 复杂值（对象/数组/脱敏 preview/meta）单元格不进 inline 编辑，点击开一个轻量「单元格 JsonEditor 弹层」（复用 json-editor.tsx，Sheet 或 Popover 容器），保存同样走 updateItem。
  - 每行 key={item.id} + 编辑态 local，避免跨行串状态；行级 remount key 用 item.id 即可。

③ 增行 / 删行。
  - 增行：表格底部「+ 新增行」按钮 → 调新建的 createItem 端点插入一条空白 item（input_payload 至少 {第一个var列: ''} 或 {}），刷新后该行进入可编辑；批量补录仍走 bulk-import-modal。
  - 删行：操作列垃圾桶图标 → confirm-dialog（core/components/common/confirm-dialog.tsx）二次确认 → 调 deleteItem 端点 → invalidate items + dataset（item_count 变化）。

④ 后端端点选型：【逐条 updateItem（复用现有）+ 新增 createItem/deleteItem 两个单条端点】，不做批量 update 端点。理由：
  - 行内失焦保存天然是「一次改一格 = 一条 update」，updateItem（service.py:205）已满足且【不重跑 PII】（关键：sampled 脱敏行被 round-trip 不会被二次 mask 破坏），直接复用，零后端改动。
  - 批量 update 端点只有「Excel 整表粘贴覆盖」才需要，那场景已由 bulk-import 覆盖（新增语义），不值得为它建批量 update 契约 + 处理逐行 PII 差异，YAGNI。
  - 必须新增两个端点（现状缺）：
    · POST /v1/admin/datasets/{dataset_id}/items（单条 create）→ service.create_item：构造 DatasetItem(source_call_log_id=None, input_payload, expected_output, meta={source:'manual_add',...})，对 input_payload/expected_output 跑一次 apply_pii_strategy_dict（与 bulk-import 一致，默认 mask），flush 后 count(*) 重算 ds.item_count（抄 service.py:383-390），返 DatasetItemItem。
    · POST /v1/admin/datasets/items/{item_id}/delete → service.delete_item：按 id 删 DatasetItem，回查 dataset_id 后 count(*) 重算 item_count。
    · api.py 两个 handler 零业务（校验 + 调 service + Result.ok），权限 datasets:write/delete。schemas.py 加 CreateItemRequest{input_payload, expected_output?, meta?, pii_strategy='mask'}。
  - service 注意：create/delete 必须维护 item_count（现状只有 sample/bulk-import 维护），否则列表角标漂移。

⑤ 技术选型结论：手写 editable table（基于 DataTable 视觉语言自建 editable variant），不引第三方表格库。权衡：DataTable 是纯展示（data-table.tsx 无编辑态），强行塞 cell-edit 会污染通用组件 → 故新建 dataset-spreadsheet.tsx 专用组件，复用 DataTable 样式 token（thead 暖底、divide-stone-100、text-[12.5px]、minWidth 横滚）+ core/ui/input.tsx + json-editor.tsx + confirm-dialog.tsx，视觉一致但不耦合 DataTable API。规约「列表复用 DataTable」指【只读列表】；可编辑电子表格是另一种交互形态，自建合规。

【前端服务层】services/dataset.ts 加 createItem(datasetId, req)→POST .../items，deleteItem(itemId)→POST .../items/{id}/delete；types/dataset.ts 加 CreateItemRequest。HTTP 只在 services/，组件调 datasetApi.*。

【数据流】dataset-detail-page items tab 渲染 <DatasetSpreadsheet items={itemsQ.data} datasetId={dsId} onChanged={invalidate}/>；内部 useMutation(updateItem/createItem/deleteItem) + qc.invalidateQueries(['datasets',dsId,'items'] 与 ['datasets',dsId])。雪花 id 全程 string（EntityId），禁 Number()。

【与现有组件关系 — 并存而非替代】
  - dataset-item-editor-drawer.tsx【保留】：「整条/全字段 JSON 高级编辑」出口（meta 复杂结构、整 input_payload 重构、脱敏行不便 inline 改时）。电子表格的复杂值弹层可直接复用它，或操作列留「高级编辑」铅笔仍开抽屉。表格管「快改单格」，抽屉管「整条精修」，互补。
  - bulk-import-modal.tsx【保留】：批量 Excel/JSONL 导入入口不变（新增语义），电子表格「+新增行」是单条补录，不冲突。
  - 唯一替换：dataset-detail-page.tsx:375-383 的只读 DataTable（items 分支）换成 DatasetSpreadsheet；itemCols（:116-177）随之删除或迁入新组件。runs tab 的 DataTable 不动。

**文件**：frontend/src/system/datasets/components/dataset-spreadsheet.tsx (新建：editable table 主体 + EditableCell + 复杂值弹层), frontend/src/system/datasets/utils/dataset-spreadsheet.ts (新建：inferColumns 动态列推断 + 单元格取值/写回 helper，复用 dataset-xlsx cellOf/parseCell 思路), frontend/src/system/datasets/pages/dataset-detail-page.tsx (items 分支 DataTable→DatasetSpreadsheet；删 itemCols), frontend/src/system/datasets/services/dataset.ts (加 createItem/deleteItem), frontend/src/system/datasets/types/dataset.ts (加 CreateItemRequest), backend/chameleon-system/src/chameleon/system/datasets/api.py (加 create_item / delete_item 两个零业务 handler), backend/chameleon-system/src/chameleon/system/datasets/service.py (加 create_item / delete_item，维护 item_count；复用 apply_pii_strategy_dict), backend/chameleon-system/src/chameleon/system/datasets/schemas.py (加 CreateItemRequest)

**迁移**：无。input_payload / expected_output / meta 三列已在 dataset_items（dataset.py:59-63），create/delete/update 全部用现有列。create/delete 仅需在 service 维护冗余 item_count（count(*) 重算，无 schema 变更）。【绝不】触碰 newapi 的 p27_a01_model_upstream_fields 或 model_def/factory/providers 文件。

**风险**：列推断处理 sampled 脱敏嵌套 input_payload（{hash,preview} 对象）与 manual 扁平 {user_input} 混存：必须区分 preview-only 只读 vs 可编辑文本，否则把脱敏对象当文本编辑会破坏结构或泄露语义。设计已用「含 preview 字段→只读灰显」规避。；失焦保存 + 乐观更新需稳妥回滚（onError 还原 cache），否则网络抖动留下脏单元格；编辑态 local state 必须惰性 useState 初始化、按 item.id remount，避免 set-state-in-effect（eslint error）。；新增 create/delete 必须维护冗余 item_count（现状仅 sample/bulk-import 维护），漏维护→列表角标与实际样本数漂移。；createItem 默认 mask PII 会改写用户手填含邮箱/手机号的输入，需 UI 给 PII 提示；而 updateItem 改其它格【不】重跑 PII，二者策略不一致需文档说明。；动态列数不定，列多时横向滚动（minWidth 模式）体验下降；超宽 dataset 需设每列最小宽 + 关键列冻结（本期可不做冻结，标记后续）。；GSB「模型回答拆 A/B 列 + 分数列」是运行态数据，强塞样本编辑表会混淆样本/运行两层语义；设计已切割（本领域只做样本列），但与计划 §H2 文案有出入，落地时需对齐。

**分期建议**：按 D4/分期表后置到【第 3 期（P2，差异化）】——计划 §五明确「H2 AI 扩样 + 电子表格编辑」属第 3 期，且执行进度表第 9 行 H2 标注「电子表格编辑留后续」已显式 defer。本期（按 /loop SSOT）不做。理由：① 这是 PromptPilot 级差异化锦上，非可用性底线（B 全字段抽屉 + C Excel 导入已让「能编辑」闭环可用）；② GSB 模式下「模型回答拆 A/B 列 + 分数列」依赖模块 G judge 多模式（计划 §H2 提到模型回答列/分数列），且模型回答/分数严格说属运行态非样本态，本设计先只做「{{var}}+理想回答+meta」样本编辑，模型回答/分数列留到 G 落地后接 run-detail 数据；③ 当前 working tree 有 newapi 并行改动，电子表格是纯前端 + datasets 域独立改动，与之零交叉，可安全排到 newapi 合并后单独开干。建议落地顺序：先补 create/delete 两端点（小、独立、也利于其它入口）→ 再做前端电子表格组件。

---

## H3-version-lineage-and-optimization-persistence　effort=M　依赖=[]

**现状**：现状（H3 已"半成品"，只差落库与版本链）：

- 优化器纯计算、不落库：`backend/chameleon-system/src/chameleon/system/datasets/optimizer.py:31` `optimize_run_prompt(session, run_id)` 取低分样本（阈值 0.6，最多 12 条，optimizer.py:27-28）→ `_llm_optimize`（optimizer.py:82，走 `channel='eval'` + `set_trace_context`/`reset_trace_context`，optimizer.py:96-110）→ 返回 dict `{run_id, original_prompt, optimized_prompt, report, weak_count}`（optimizer.py:66-72）。**没有任何 INSERT/UPDATE**。
- 端点直透不落库：`backend/chameleon-system/src/chameleon/system/datasets/api.py:313` `POST /v1/admin/datasets/runs/{run_id}/optimize` → `optimize_run_prompt` → `OptimizeResult(**data)`（同步阻塞返回，10-30s）。schema `OptimizeResult` 在 `schemas.py:126`。
- DatasetRun ORM 缺版本链字段：`backend/chameleon-data/src/chameleon/data/models/dataset.py:66` `DatasetRun` 已有 `prompt_override`(Text, :81)、`model_override`(:80)、`agent_key`(:79)、`summary`(JSON, :89)，但**无** `optimized_prompt` / `optimization_report` / `parent_run_id`。
- run 创建入口可直接复用：`backend/chameleon-system/src/chameleon/system/datasets/runner.py:45` `run_dataset(...)` 已接 `prompt_override` 参数（runner.py:51, 92），建 run 在 runner.py:87-96。**用优化后 Prompt 建新 run 不需要任何引擎改造**，只需把 `optimized_prompt` 当 `prompt_override` 传进去 + 记 `parent_run_id`。
- compare 已具版本对比雏形：`run-compare-matrix.tsx:45-61` 前端已算 win/tie/loss（以第一个 run 为基准逐样本比分），`service.compare_runs`（service.py:535）返回 rows+runs。**"版本→评分变化"只需把 parent_run_id 链上的 run 喂进现有 compare**。
- 前端：`optimize-modal.tsx`（同步 mutation，optimize-modal.tsx:28-33，已有报告+前后 Prompt 双栏 diff 展示），入口在 `run-detail-drawer.tsx:195`（"智能优化"按钮）。service `datasetApi.optimizeRun`（dataset.ts:47），类型 `OptimizeResult`（types/dataset.ts:159）。

可复用基础：
- 异步框架：项目**无 arq/celery/redis-queue**，统一用 `asyncio.create_task` + 自管 `AsyncSessionLocal` session。范本 `backend/chameleon-system/src/chameleon/system/kbs/evaluation_service.py:147` `spawn_eval` → `run_evaluation`（kbs/evaluation_service.py:151，status=running→success 回写、分阶段开 session，db.py:30 `AsyncSessionLocal`）。
- 迁移头：当前 head = `p27_a01_model_upstream_fields`（无人 down_revision 指向它，已确认），范本 `migrations/versions/p26_g01_run_item_judge_fields.py`（同样 add_column nullable JSON/Text）。

**方案**：总体定调：**优化产出落到 DatasetRun 自身（加 3 列），版本链用 parent_run_id 自引用**——不新建 prompt_optimization 表（YAGNI：一次优化 = 一个产出，与 run 1:1；落 run 上后"用优化 Prompt 建新 run"天然形成 run→run 链）。**第 3 期同步够用，异步留接口位但本期不做**（理由见 phase_advice）。

═══ ① DatasetRun 加 3 列（迁移见 migration 段）═══
在 `models/dataset.py` DatasetRun 加（紧跟 prompt_override 之后，dataset.py:81）：
- `optimized_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)` —— H3 LLM 重写产出
- `optimization_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)` —— 结构化报告 `{report: str, weak_count: int, threshold: float, model_used: str|None, generated_at: iso}`（JSON 而非裸 text，给前端结构化展示 + 后续可加字段不再迁移）
- `parent_run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("dataset_runs.id", ondelete="SET NULL"), nullable=True)` —— 版本链：本 run 由哪个 run 优化而来。SET NULL 而非 CASCADE（删父 run 不连带删子版本，保留谱系断点）

语义约定（写进 docstring）：
- `optimized_prompt`/`optimization_report` 非空 = 这个 run **被优化过**（产出挂在被优化的 run 上）。
- `parent_run_id` 非空 = 这个 run **是优化产物**（用父 run 的 optimized_prompt 重新跑出来的）。
两者互补：优化动作落在父 run（产出报告），重跑结果是新子 run（parent_run_id 指父）。

═══ ② 优化落库 + 一键"用优化 Prompt 建新 run"═══

(a) optimizer 落库改造（`optimizer.py:optimize_run_prompt`）：
计算 `result` 后，在返回前把 `optimized_prompt` + `optimization_report` 写回**被优化的 run 行**（run 对象已在 optimizer.py:33-37 查出）：
```
run.optimized_prompt = result.get("optimized_prompt", "")
run.optimization_report = {
    "report": result.get("report", ""),
    "weak_count": len(rows),
    "threshold": LOW_SCORE_THRESHOLD,
    "generated_at": datetime.now(timezone.utc).isoformat(),
}
await session.commit()
```
端点签名/返回不变（仍 `OptimizeResult`），但**幂等**：重复点"智能优化"覆盖产出（这是改写，无需历史多版本报告）。`OptimizeResult` 已含全部字段，前端展示无需改。

(b) 新端点"用优化 Prompt 建新 run"（核心闭环）：
`POST /v1/admin/datasets/runs/{run_id}/apply-optimized`（api.py 新增，紧跟 optimize 端点 api.py:321 之后）。
- handler 零业务：取 run_id → 调新 service `apply_optimized_run`（下沉到 service.py 或新 `optimizer.apply_optimized_run`）→ 包 `Result.ok(DatasetRunDetail...)`。
- service 逻辑：
  1. 查父 run，校验 `run.optimized_prompt` 非空（否则 `BusinessError("该运行尚未优化，先点智能优化")`）。
  2. 调 `runner.run_dataset(session, dataset_id=父run.dataset_id, name=f"{父run.name} · 优化v{n}", model_override=父run.model_override, prompt_override=父run.optimized_prompt, judge=父run.judge, agent_key=父run.agent_key, eval_template_id=...)` —— **完全复用现有 runner，零引擎改造**。注意 agent_key 路径下 prompt_override 不生效（runner.py:123-132），故 apply 仅对**模型直调 run** 有意义，service 层校验 `父run.agent_key is None`，否则报错引导。
  3. 拿到新 run 后 `new_run.parent_run_id = run_id; await session.commit()`。
  4. 返回 `DatasetRunDetail`。
- 入参 body：可选 `name`（前端可改命名），缺省自动版本号。
- **版本号 n**：service 查 `count(*) where parent_run_id chain 含本 dataset 的优化产物` 或简单地 `子 run 数 + 1`，仅用于默认命名，不入列。

(c) 前端闭环（`optimize-modal.tsx`）：
产出页（optimize-modal.tsx:68 result 分支）底部加按钮"用优化后 Prompt 跑新一轮"→ 新 mutation `datasetApi.applyOptimized(runId)` → 成功后 `toast` + 关闭 modal + invalidate runs 列表 query（`['ds-runs', datasetId]`）让新 run 出现在运行 tab。service `dataset.ts` 加 `applyOptimized: (runId) => post<DatasetRunDetail>(\`${BASE}/runs/${runId}/apply-optimized\`, {})`。

═══ ③ run-compare-matrix 关联"版本→评分变化"═══
最小改动复用现有 compare（前端已算 win/tie/loss，run-compare-matrix.tsx:45-61）：
- `DatasetRunDetail` schema（schemas.py:198）加 `parent_run_id: int | None`，`DatasetRunRow`（schemas.py:180，compare 返回用这个）加 `parent_run_id: int | None` + `optimized_prompt` 是否存在的轻量标记（可只透 `has_optimization: bool`，避免把长 prompt 塞进列表）。前端 types/dataset.ts 同步加。
- 运行 tab 里给"优化产物 run"打版本徽标：父 run 名旁显示"← 优化自 {parentName}"或链式版本树（run-stats-overview/运行列表层，按 parent_run_id 分组）。
- 一键对比：优化产物 run 详情/列表加"对比上一版本"按钮 → 把 `[parent_run_id, run_id]` 喂进现有 `RunCompareMatrix`（runIds prop，run-compare-matrix.tsx:21）→ 现成 win/tie/loss 即"胜率提升"。**无需新增 compare 后端逻辑**。
- 增强（可选）：compare-matrix 顶部胜负条已有（matrix.tsx:71-114），父子对比时把基准固定为 parent（runs[0]=parent），文案改"优化后 vs 优化前"。

═══ ④ 异步必要性结论：本期同步够用，留位不实现 ═══
- 现状单轮优化 = 1 次 LLM 调用（optimizer.py:106 单 ainvoke），10-30s，前端已用 `mut.isPending` loading 态扛住（optimize-modal.tsx:56-65 文案"10-30秒"）。FastAPI 端点同步 await 在该时长可接受，无需异步。
- "用优化 Prompt 建新 run"复用 `runner.run_dataset`，**该 run 流程本身已是同步阻塞**（runner.py 全程 await，最多 500 item，runner.py:42），与现有 `POST /{id}/run` 端点同步行为一致——保持同步即可，不引入新机制。
- **何时需异步**：D7 已定"只做 Prompt 改写 + 报告 + diff + 版本"，不做多轮迭代优化。若**未来**做"多轮自动优化"（optimize→apply→再 optimize→收敛），那是分钟级长任务，届时按 `kbs/evaluation_service.py:147` 的 `spawn_eval` 范式（`asyncio.create_task` + `AsyncSessionLocal` + run.status 轮询）加，**当前不预实现**（避免 set-state-in-effect 轮询 + 空跑框架）。为此 ① 的 `optimization_report` 用 JSON 而非 text，给未来多版本/进度态留 schema 弹性。

**文件**：backend/chameleon-data/src/chameleon/data/models/dataset.py, backend/migrations/versions/p27_h01_run_optimization_lineage.py (新建), backend/chameleon-system/src/chameleon/system/datasets/optimizer.py, backend/chameleon-system/src/chameleon/system/datasets/api.py, backend/chameleon-system/src/chameleon/system/datasets/service.py, backend/chameleon-system/src/chameleon/system/datasets/schemas.py, frontend/src/system/datasets/services/dataset.ts, frontend/src/system/datasets/types/dataset.ts, frontend/src/system/datasets/components/optimize-modal.tsx, frontend/src/system/datasets/components/run-detail-drawer.tsx, frontend/src/system/datasets/components/run-compare-matrix.tsx

**迁移**：需要 alembic 迁移。新建 `backend/migrations/versions/p27_h01_run_optimization_lineage.py`：
- revision: "p27_h01_run_optimization_lineage"
- down_revision: "p27_a01_model_upstream_fields"（接在 newapi 迁移之后；当前确认的 head，避免与并行 newapi 工作冲突造成多头）
- upgrade(): 对 dataset_runs 表 add_column 3 列（全 nullable，存量零影响，参照 p26_g01 风格）：
  - `optimized_prompt` sa.Text() nullable
  - `optimization_report` sa.JSON() nullable
  - `parent_run_id` sa.BigInteger() nullable + 单独 op.create_foreign_key("fk_dataset_runs_parent", "dataset_runs", "dataset_runs", ["parent_run_id"], ["id"], ondelete="SET NULL")（自引用 FK）；可选 op.create_index("ix_dataset_runs_parent", "dataset_runs", ["parent_run_id"]) 加速版本树查询
- downgrade(): 反序 drop_index → drop_constraint → drop_column ×3
注意：Postgres 自引用 FK 直接 create 即可（非 SQLite，无需 batch_alter_table；本项目生产是 Postgres，规约里 SQLite batch 仅对 SQLite 测试库，但 add_column + create_foreign_key 在两者都安全分开写）。

**风险**：自引用 FK ondelete=SET NULL：删父 run 后子版本 parent_run_id 变 NULL，版本链断点——前端需容忍 parent_run_id 指向已删 run 的情况（显示'原版本已删除'而非崩溃）；apply-optimized 复用 runner.run_dataset 是同步阻塞：dataset item 多时端点耗时长（最多 500 item × LLM 延迟），与现有 POST /{id}/run 同步行为一致但需前端 loading 态兜住；若 item 量大用户体验差则是触发异步化的信号；optimize 落库改为幂等覆盖：重复点'智能优化'会覆盖上次 optimized_prompt/report，不保留历史多版本报告——符合'改写'语义，但若用户期望多版本优化历史则需求不匹配（当前 D7 范围不做）；并行 newapi 迁移风险：若 newapi 工作在合并前又叠加了新迁移使 head 变化，p27_h01 的 down_revision 需对齐到届时真实 head，否则 alembic 多头；落地前必须重新确认 alembic heads；DatasetRunRow（compare/list 复用）若直接塞 optimized_prompt 长文本会撑大列表 payload——设计已规避：列表只透 has_optimization 标记 + parent_run_id，完整 optimized_prompt 仅 DatasetRunDetail 返

**分期建议**：本期可做（属第 3 期 H3 收尾，plan §H3 + D7 范围内）。理由：① 落库 + 版本链是 H3 已开工功能的"最后一公里"，optimizer/optimize-modal 已存在只差持久化，成本低收益直接（当前优化产出一刷新就丢）。② 完全复用现有 runner + compare-matrix，零引擎改造、零新框架。③ 与并行 newapi 工作物理隔离：只碰 datasets 域 + 自建迁移接在 p27_a01 之后，不触 model_def/factory/providers。

按 plan 后置/收窄的部分：
- **异步多轮优化后置**（D7 已定不做多轮迭代）：本期只做"单次优化落库 + 一键建新 run + 版本对比"，同步实现。多轮自动收敛留到未来，届时按 kbs spawn_eval 范式加，不预建空框架。
- **agent_key run 的优化**：apply-optimized 仅对模型直调 run 生效（runner agent 路径 prompt_override 不透传），service 层校验拦截 + 前端引导，不在本期为 agent 路径强行接 prompt 注入（那是 graph 域改造，超出 H3）。
- **prompt_optimization 独立表**：不做，落 run 3 列即可（1:1 关系，YAGNI）。

---

## H1-playground-vars-rewrite　effort=M　依赖=[]

**现状**：H1 已落地的部分（commit dc0f020）：「存为评测样本」按钮 + Modal 已做完，锚点 frontend/src/system/playground/components/message-thread.tsx:270-287（按钮）、frontend/src/system/playground/components/save-as-sample-modal.tsx（整文件）、prevUserOf message-thread.tsx:79-85（取上一条 user 文本预填）。剩两项：{{var}} 变量抽取填值、基于回答改写。

可复用基础（已确认存在，别重造）：
- Composer：frontend/src/system/playground/components/composer.tsx（整文件 73 行，本地 input/attachments state，doSend 23-33；发送签名 onSend(text, attachments)）。
- ParamPanel：frontend/src/system/playground/components/param-panel.tsx（System Prompt textarea 在 116-124，set() helper 44-47，已有 model/kb 选择器）。
- chat store：frontend/src/core/stores/chat/{actions,state}.ts。System Prompt 经 PlaygroundParams.system_prompt 流转（types/playground.ts:49-59）；updateParams(columnId, params) 在 actions.ts:327-338；runInvoke 拼请求体 actions.ts:173-246，system_prompt 取 params.system_prompt（actions.ts:190-191），支持 overrides.system_prompt（translate 已用此机制做 transient，actions.ts:582-608 + 198 persist_config=false）。
- playground-page.tsx:227 applyPreset 已示范「改写 system_prompt → updateParams」回灌路径；metaToParams 在 84-104。
- ModelPicker 公共组件已存在：frontend/src/core/components/common/model-picker.tsx（onChange(model_code)，模块 A 产出）。
- 后端 channel='eval' 基础设施齐全：data/constants/channels.py:21 Channel.EVAL；eval 渠道 LLM 调用范式见 datasets/ai_generate.py:94-108 与 datasets/optimizer.py:96-110（set_trace_context(TraceContext(channel=Channel.EVAL.value, app_id="__eval__", session_id=f"eval-...")) → get_llm(None).ainvoke([HumanMessage]) → reset_trace_context，复用切面不新增）。get_llm 同步工厂在 integrations/llms/factory.py:149 返 BaseLLM。
- 后端 playground 域：backend/.../system/playground/{api,service}.py，invoke 端点 api.py:51-81，权限 require_permission("playground:invoke")。
- 前端 HTTP 封装 get/post（@/core/lib/request，已脱 Result 外层）；dataset.ts:44-48 示范 aiGenerate/optimizeRun 非流式 POST。

**方案**：两项独立功能，分别设计。均不碰 working tree 的 newapi 文件（model_def.py/factory.py/providers/api.py/p27_a01），不依赖其字段。

═══ ① {{var}} 变量抽取 + 填值 UI（纯前端，零后端、零迁移）═══

数据流定位：变量声明源 = System Prompt（ParamPanel 的 system_prompt）。识别 {{name}} → 暴露成可填字段 → 发送时把占位符替换成填的值。替换发生在「拼请求体 system_prompt」这一层，不改 params.system_prompt 原文（原文保留 {{var}} 模板，值单独存）。

A. 纯函数工具（新建 frontend/src/system/playground/utils/template-vars.ts + 同目录 .test.ts）
   - extractVars(text): string[] —— 正则 /\{\{\s*([a-zA-Z0-9_一-龥]+)\s*\}\}/g 抽取去重变量名（保序）。
   - fillTemplate(text, values): string —— 每个 {{name}} 替换成 values[name]，未填的保留原占位符（不静默清空）。单一职责、可单测。

B. 变量值存哪：扩 PlaygroundParams 增 var_values?: Record<string,string>（types/playground.ts:49-59）。变量值是会话级配置，跟 system_prompt 同源同生命周期，跟 params 走。state.ts:66-72 newParams() 补默认 {}。var_values 不进 InvokeRequest（types/playground.ts:61-78 不加字段）——只在前端 runInvoke 内部用于拼 system_prompt，后端无感知。

C. 填值 UI（新建 frontend/src/system/playground/components/template-vars-panel.tsx）
   - props { systemPrompt; values; onChange }。用 extractVars(systemPrompt) 派生变量列表（useMemo，非 state，避免 set-state-in-effect）。无变量返 null。
   - 每变量一行：变量名 chip {{name}} + 文本 Input 直填（受控，写 values[name]）。复用 ParamPanel text-[12px]/stone 配色，禁硬编码色。
   - 渲染位置：插在 param-panel.tsx System Prompt 块（115-124）正下方，<TemplateVarsPanel systemPrompt={params.system_prompt} values={params.var_values ?? {}} onChange={v => set('var_values', v)} />。

D. 发送时替换（改 frontend/src/core/stores/chat/actions.ts runInvoke）
   - actions.ts:190-191 现为 system_prompt: overrides?.system_prompt ?? params.system_prompt ?? undefined。
   - 改为局部 const effectiveSystem = overrides?.system_prompt ?? fillTemplate(params.system_prompt ?? '', params.var_values ?? {})，请求体用 effectiveSystem。translate 等 transient override 仍走 overrides 分支不受影响。
   - persist_config 不变（actions.ts:198）。

E. resume 恢复：var_values 仅靠前端 localStorage 持久化（state.ts persistChat 已整体存 params，含 var_values，无需改持久化逻辑也无需动后端 SessionConfig）；meta.config 里仍存的是替换后的 system_prompt 实值（用于溯源）。metaToParams（playground-page.tsx:84-104）不强制恢复 var_values（localStorage 已兜，跨设备恢复时丢值是可接受降级）。

F. 边界：未填值 fillTemplate 保留 {{name}} 原样发出（用户从回答可见漏填，比静默空串好）；未填 Input 给 placeholder「未填，将原样发送」。对比模式每列独立 params（含 var_values）天然按列隔离。

═══ ② 基于模型回答改写 Prompt（轻量按钮 + 后端 /prompt/rewrite）═══

与 H3 optimizer 的本质区分（写进代码注释避免后人混淆）：
   - H3 optimizer（datasets/optimizer.py，POST /datasets/runs/{run_id}/optimize）：run 级/整集级——汇总「整个评测集低分样本共性缺陷」（消费 low_score_item_ids，MAX_WEAK_SAMPLES=12），多样本输入，重型，产出 optimized_prompt + 优化报告 +（未来）版本链，锚一个 DatasetRun。
   - H1 rewrite（本设计，POST /playground/prompt/rewrite）：单条/即时——只看「当前 System Prompt + 一条模型回答 + 用户改写需求」，零数据集/零 run 上下文，单次 LLM 调用，产出「改写后新 System Prompt 文本」，直接回灌 ParamPanel，不落任何持久化表。
   两者各自独立端点/独立 service/不互相 import，仅共享 channel='eval' 的 TraceContext 范式。

后端（backend/.../system/playground/）：
   - service.py 新增 async def rewrite_prompt(session, *, current_prompt, answer, instruction, model_code=None) -> str：
     · 组中文 prompt：给定「当前 System Prompt + 模型最近一次回答 + 用户改写需求」，让 LLM 只输出改写后的完整 System Prompt 纯文本（不要解释、不要 JSON 包裹，避免脆弱解析）。
     · 复用 eval 范式：request_id=uuid4().hex；set_trace_context(TraceContext(channel=Channel.EVAL.value, app_id="__eval__", session_id=f"eval-rewrite-{request_id[:8]}", request_id=...))；llm=get_llm(model_code)（前端传选中模型 code，None 走默认）；ai=await llm.ainvoke([HumanMessage(content=prompt)])；finally reset_trace_context。
     · 返回 str(ai.content).strip()；空则 raise BusinessError(ResultCode.Fail, message="改写失败，请调整需求后重试")。业务逻辑全在 service，API 零逻辑。
   - api.py 新增：PromptRewriteRequest{current_prompt: str=""; answer: str; instruction: str=Field(min_length=1); model_code: str|None=None}；PromptRewriteResponse{rewritten_prompt: str}。@router.post("/prompt/rewrite", response_model=Result[PromptRewriteResponse])，Depends(require_permission("playground:invoke"))，校验后调 service.rewrite_prompt，Result.ok(...)。非流式（单段短输出 + 需 diff 预览，SSE 无收益）。

前端：
   - service：playground.ts 新增 rewritePrompt(req): Promise<{rewritten_prompt:string}> = post('/v1/admin/playground/prompt/rewrite', req)（@/core/lib/request，自动脱 Result）。
   - 入口按钮：message-thread.tsx 在「存样本」按钮（270-287）旁加 Wand2 图标按钮「改写提示词」，title「基于此回答改写 System Prompt（轻量）」，点击开新 Modal。message-thread.tsx 持 rewriteOpen state（与 saveOpen 286 并列），渲染 <RewritePromptModal columnId answer={msg.content} .../>；columnId 已是 MessageBubble 现有 prop（109-119）。
   - 新建 rewrite-prompt-modal.tsx（照抄 save-as-sample-modal.tsx 结构）：props {columnId; answer; onClose}。useChatStore 取该列 params（current_prompt=params.system_prompt；model_code 由前端 model_id→code 映射后传，后端 None 容错兜底）。改写需求 instruction 用 Textarea，空禁提交。useMutation 调 rewritePrompt；onSuccess 拿 rewritten_prompt → 预览 diff（旧→新）+「应用」按钮 → updateParams(columnId, {...params, system_prompt: rewritten_prompt})（复用 applyPreset 同路径）→ toast.success「已更新 System Prompt」→ onClose。mut.isPending 显「改写中…」。

交互闭环：聊 → 不满意回答 → 点「改写提示词」→ 写「让回答更简短、加引用」→ LLM 出新 System Prompt → 预览 diff → 应用 → ParamPanel 即时更新 → 重发验证。全程挂 channel='eval' 进 Trace（成本可统计、可关闭）。

**文件**：frontend/src/system/playground/utils/template-vars.ts (新建), frontend/src/system/playground/utils/template-vars.test.ts (新建), frontend/src/system/playground/types/playground.ts (PlaygroundParams 加 var_values), frontend/src/system/playground/components/template-vars-panel.tsx (新建), frontend/src/system/playground/components/param-panel.tsx (插入 TemplateVarsPanel), frontend/src/core/stores/chat/state.ts (newParams 补 var_values 默认), frontend/src/core/stores/chat/actions.ts (runInvoke 用 fillTemplate 拼 system_prompt), frontend/src/system/playground/components/rewrite-prompt-modal.tsx (新建), frontend/src/system/playground/components/message-thread.tsx (加改写按钮 + Modal 挂载), frontend/src/system/playground/services/playground.ts (加 rewritePrompt), backend/chameleon-system/src/chameleon/system/playground/api.py (加 /prompt/rewrite 端点 + 请求/响应 schema), backend/chameleon-system/src/chameleon/system/playground/service.py (加 rewrite_prompt)

**迁移**：无。{{var}} 纯前端（var_values 走前端 localStorage 持久化，state.ts persistChat 已整体存 params，不加 DB 列、不动后端 SessionConfig）；rewrite 端点不落库（即时改写，结果直接回灌前端 ParamPanel），无 alembic 迁移，不依赖 working tree 的 p27_a01 newapi 迁移。

**风险**：rewrite 的 model_code 来源：ParamPanel 选的是 model_id（雪花 string），后端 get_llm 要 model_code。前端需先把 model_id→code（store 或 ModelPicker 已知映射）再传，后端按 model_code 容错 + None 兜底默认模型。建议前端传 code、后端 None 兜底，避免精度/不匹配问题。；改写质量依赖 LLM 不加解释/不 JSON 包裹——prompt 需强约束「只输出改写后的 System Prompt 纯文本」，对空/异常输出 raise BusinessError 由全局 handler 兜成失败 Result（不在 API try/except 吃异常）。；var_values 仅 localStorage 持久化：跨设备 / 清缓存后 resume 会话会丢变量值（system_prompt 模板原文仍在 params，可重填）。若后续要求跨设备恢复变量值，再评估给后端 SessionConfig（service.py:53-71）加 var_values 字段——本期不做，避免动后端 schema。；extractVars 正则含中文区间 [一-龥]：需确认 ParamPanel/Composer 的变量命名约定（是否允许中文变量名）；若只允许英文标识符，收窄正则避免误匹配。

**分期建议**：本期可做。两项都是 H1 收尾（H1 主体 dc0f020 已交付），P1·M，无强依赖：① {{var}} 纯前端零后端零迁移可独立先落；② rewrite 端点完全复用已就位的 channel='eval' 范式（ai_generate.py/optimizer.py 已示范，Channel.EVAL 常量已登记），后端只加一个非流式端点 + 一个 service 函数，前端一个 Modal + service 方法。与 newapi gateway 工作零文件重叠。按 D6（AI 能力默认走系统默认 chat 模型 + eval 渠道、可统计）与 D7（只做 Prompt 改写不做微调）边界，本设计严格落在轻量改写一侧，与 H3 optimizer 划清。

---

## eval-scoring-dsl　effort=L　依赖=['eval-judge-contract']

**现状**：关键发现：plan 描述的 G2「JudgeResult 契约升级」其实没真正落地——`backend/chameleon-system/src/chameleon/system/datasets/judges.py` 仍是旧契约（`async def judge(expected, actual) -> float | None`，JUDGES 仅 exact_match/contains/llm_judge 三函数，llm_judge:49 还是死返 0.5 的占位），真正的 AI 评分是 runner.py 把 `judge=='llm_judge'` 内联特判走 `_llm_judge_score`（runner.py:133-137、267-298），并不存在 `JudgeResult` 类型。

已铺好的可复用基础（别重造）：
- DB 列已就位（migration p26_g01_run_item_judge_fields，已发布）：`dataset_run_items.score_reason`(Text) / `field_scores`(JSON) / `reference_output`(JSON)，见 `backend/chameleon-data/src/chameleon/data/models/dataset.py:130-135`；schemas 出参字段已加 `backend/chameleon-system/src/chameleon/system/datasets/schemas.py:160-163`；前端 run-detail 已有 score_reason 展示位 `frontend/src/system/datasets/components/run-detail-drawer.tsx:393-404`（field_scores 尚无渲染）。
- eval 渠道 LLM 调用范式已成熟：`runner.py:267-321`(_llm_judge_score + _parse_judge_json 容错抽 JSON) 与 `optimizer.py:82-124`(_llm_optimize 自建 TraceContext + channel=Channel.EVAL.value + reset)，自然语言规则函数照抄此范式即可，`Channel.EVAL` 见 `backend/chameleon-data/src/chameleon/data/constants/channels.py:21`。
- 多字段聚合参照结构：`template_scoring.py:62-132`（per_metric_sums/counts + weighted_total 聚合，红线禁改 weight/算子注册表，只读参照其「逐字段算分→汇总」骨架，不改不依赖它）。
- import-linter 两契约只管 core/data/integrations/engine（`backend/pyproject.toml:73-104`），chameleon-system 不在分层契约内，故 `datasets/dsl.py` 可像 runner/optimizer 一样自由 import `chameleon.integrations.llms.factory`，无越层风险。
- 前端 judge 选择现状：`frontend/src/system/eval_jobs/components/eval-job-form-modal.tsx:45-58` 的 JUDGE_META（中文名+说明）+ 278 行裸 Select，数据源 `GET /v1/admin/datasets/judges`（`api.py:68-72` → `judges.list_judges`）。无 judge_config 任何字段（全仓 grep 零命中）。

⚠️ 绝不碰：p27_a01_model_upstream_fields.py、model_def.py、llms/factory.py 的 newapi 改动、providers/api.py——本设计与之零交集。

**方案**：【定位】这是评测域最后/最大一项，强依赖前序「judge 契约统一」。务必先补真正的 JudgeResult 契约（plan §G line 237 承诺但未落地），DSL 只是挂在契约上的一种 judge 模式。分两步交付（本期可视化配置 / 第3期 DSL 文本解析器），见 phase_advice。

═══ 步骤 0（前置硬依赖，必须先做）：补齐 JudgeResult 统一契约 ═══
新建 `datasets/judge_contract.py`：
- `class JudgeResult(BaseModel){ score: float|None; scale: Literal['0-1','1-5']='0-1'; reason: str|None=None; field_scores: dict[str,float]|None=None }`（内部统一 [0,1] 存储——采纳 Q3 的「内部归一」结论：1-5 函数除以 5 归一进 score，scale 仅作 UI 显示标记；这样 mean_score/低分下钻/RAGAS 全沿用 [0,1]，零改动）。
- judge 协议升级：`JudgeFn = Callable[..., Awaitable[JudgeResult|None]]`，签名 `async def judge(expected, actual, *, reference=None, config=None, llm=None) -> JudgeResult|None`。
- 旧三函数（exact_match/contains/llm_judge）用适配器包成 JudgeResult（exact/contains 返 score∈{1.0,0.0}、scale='0-1'；llm_judge 把 runner 里内联的 _llm_judge_score 收口进来返 reason）。
- runner.py:102-167 改造：不再 `judge==='llm_judge'` 特判，统一 `result = await judge_fn(expected, actual, reference=item.reference_output, config=judge_config, llm=...)`，再写 `ri.score=result.score / ri.score_reason=result.reason / ri.field_scores=result.field_scores`。注意 judge 校验 `if judge not in JUDGES`(runner.py:57) 要扩到含 'dsl'/'gsb'。

═══ 模块本体：datasets/dsl.py（DSL 解析 + 字段评分 + 聚合）═══
单文件职责过重，按单一职责拆 3 文件（同目录 datasets/）：

① `datasets/dsl/parser.py`——纯文本解析（零 IO、纯函数、好测）：
   - `parse_dsl(text: str) -> DslSpec`：
     · 首行必须 `# DSL`（否则 raise DslSyntaxError，行号入错误）。
     · 每行 `字段名：函数[：参数]`（中文/英文冒号都吃，参数可空）。
     · `@` 指令行：`@聚合方式 min|max|mean|median|mode`(默认 mean)、`@格式限制 字符串|JSON|XML`、`@全部字段`/`@单个字段`（作用域开关）。
     · `<规则标签>...多行...</规则标签>` 块：累积多行自然语言交 LLM（绑定到「当前字段」或「整条」按作用域）。
   - 产出 dataclass `DslSpec{ field_rules: list[FieldRule], aggregate: str, format_constraint: str|None, scope: str, nl_rule_blocks: list[NlRuleBlock] }`；`FieldRule{ field: str, fn: str, args: list[str] }`。
   - 自定义 `DslSyntaxError(line_no, message)`（前端能定位到行）。

② `datasets/dsl/functions.py`——内置评分函数注册表（量纲 1-5，二值取 5/1，统一在 contract 层 /5 归一）：
   - 注册表 `DSL_FUNCTIONS: dict[str, DslFn]`，签名 `(field_value, expected_value, args, ctx) -> float`（返 1-5）：
     · 精确匹配 exact / 模糊匹配 fuzzy(返 1-5，可用 engine 的 jaccard_similarity 映射到 1-5 区间，注意只 import 不改) / 字数限制 length(args=min,max) / 格式限制 format(JSON/XML 可解析) / 常量等于 const_eq / 常量不等于 const_ne / 精确存在于 in_set(args 为候选集) / 精确全包括 contains_all(args 多值全包含)。
     · 自然语言规则 nl_rule：标记为 `needs_llm=True`，不在此层执行，由 evaluator 收集后批量喂 LLM。
   - 字数/格式等无需 expected 的函数允许 expected 缺失；`@格式限制` 整条不合规 → evaluator 直接给该条最低分（score=0），符合 plan line 248。

③ `datasets/dsl/evaluator.py`——编排（解析→逐字段算分→NL 规则交 LLM→聚合）：
   - `async def evaluate(expected, actual, *, spec: DslSpec, llm) -> JudgeResult`：
     · 从 expected/actual 抽对应字段（JSON dict 逐 key；复用 judges._flatten_str 兜底）。
     · `@格式限制` 先校验 actual 整体格式，不合规 → JudgeResult(score=0, reason='格式不符', field_scores={...})。
     · 每个 FieldRule 调 DSL_FUNCTIONS 算 1-5；NL 规则块批量构造 prompt 交 llm（照抄 optimizer._llm_optimize 的 channel='eval' 范式，但 llm 由 runner 注入、TraceContext 已在 runner 的 item scope 内 set，故 evaluator 内不再自建 TraceContext——避免嵌套，复用外层 eval 渠道）。
     · 聚合：把各字段 1-5 分按 @聚合方式(min/max/mean/median/mode) 汇总→总分(1-5)→/5 归一进 score；field_scores 存「字段名→归一分」；reason 拼各字段简评。
   - 对接 judge 注册表：在 judge_contract 里注 `'dsl': make_dsl_judge(spec)`——但 spec 来自 judge_config，故实际是 `async def dsl_judge(expected, actual, *, reference, config, llm)`：内部 `spec = parse_dsl(config['dsl_text'])` 后 `evaluate(...)`。

④ judge_config 透传链（无 DB 改动）：
   - `DatasetRunRequest` 加 `judge_config: dict|None=None`（schemas.py:139-149），承载 `{ dsl_text?, criteria?, few_shot? }`——规约允许的 customize 出口，复用现有 EvalTemplate.config 同款 JSON 黑盒。
   - api.py:239 run_dataset 透传 judge_config 给 runner；runner 透给 judge_fn。eval_jobs 域同理在 job 配置里存 judge_config（job 的 judge 已是 string 字段，扩一个可选 JSON 即可，落 eval_jobs 表已有的 config/meta JSON 列——需确认有，否则 eval_jobs 那侧本期可不接，仅 dataset run 接）。

═══ 前端（本期=可视化配置；DSL 文本框第3期）═══
- 把 eval-job-form-modal.tsx:278 的裸 Select 升级为「模式卡片」：精确/包含 · AI 评分(1-5+理由) · GSB 对比 · DSL 多字段，复用 JUDGE_META 扩条目。
- DSL 多字段卡片本期出「可视化逐字段配置面板」（不写 DSL 文本）：用户选「字段名（从 expected_output 的 JSON key 推断下拉）+ 函数（DSL_FUNCTIONS 中文名下拉）+ 参数 + 聚合方式」，前端组装成结构化 config（不是 DSL 文本），后端加 `build_spec_from_visual_config(config) -> DslSpec`（与 parse_dsl 并列两个入口，共用 DslSpec/evaluator）。这样可视化配置走结构化、第3期文本框走 parse_dsl，二者收敛同一 DslSpec/evaluator。
- run-detail-drawer.tsx field_scores 渲染：在 score_reason 块(393-404)旁加逐字段评分小表（field→分），复用 DataTable/简单网格。
- HTTP 仅在 services/；判分 config 类型放 eval-job types。

**文件**：backend/chameleon-system/src/chameleon/system/datasets/judge_contract.py (新建：JudgeResult + JudgeFn 协议 + 旧三函数适配器 + judge 注册表收口), backend/chameleon-system/src/chameleon/system/datasets/dsl/__init__.py (新建), backend/chameleon-system/src/chameleon/system/datasets/dsl/parser.py (新建：parse_dsl + DslSpec + DslSyntaxError), backend/chameleon-system/src/chameleon/system/datasets/dsl/functions.py (新建：DSL_FUNCTIONS 内置函数注册表), backend/chameleon-system/src/chameleon/system/datasets/dsl/evaluator.py (新建：evaluate + dsl_judge + build_spec_from_visual_config), backend/chameleon-system/src/chameleon/system/datasets/runner.py (改造 102-167：统一 JudgeResult 契约，去掉 llm_judge 内联特判，写 field_scores；扩 judge 校验), backend/chameleon-system/src/chameleon/system/datasets/judges.py (旧三函数包成 JudgeResult 适配器；list_judges 加 dsl/gsb), backend/chameleon-system/src/chameleon/system/datasets/schemas.py (DatasetRunRequest 加 judge_config), backend/chameleon-system/src/chameleon/system/datasets/api.py (run_dataset 透传 judge_config), frontend/src/system/eval_jobs/components/eval-job-form-modal.tsx (模式卡片 + DSL 可视化逐字段配置面板), frontend/src/system/eval_jobs/types/eval-job.ts (judge_config 类型), frontend/src/system/datasets/components/run-detail-drawer.tsx (field_scores 逐字段渲染), frontend/src/system/datasets/services/*.ts 或 eval_jobs/services (judge_config 透传，HTTP 只在 services)

**迁移**：无。三列（score_reason/field_scores/reference_output）已由已发布迁移 p26_g01_run_item_judge_fields 加好，model+schema 字段也已就位。judge_config 走 DatasetRunRequest 入参 + 复用 EvalTemplate.config 同款 JSON 黑盒，不落新列。⚠️ 若 eval_jobs 域要持久化 judge_config 且其表无现成 config/meta JSON 列，则需一支迁移——但本期建议 eval_jobs 侧先不持久化（仅 dataset 即时 run 接 DSL），从而完全零迁移；真要做时 revision 链接当前 head（避开 p27_a01 newapi 那支），用 batch_alter_table（SQLite 安全）。

**风险**：JudgeResult 契约升级触碰 runner.py 评分热路径（102-167）与 eval_jobs 复用同一 judge——必须保旧三函数向后兼容（适配器包装），否则击穿存量 run；改造后跑现有 dataset run e2e 回归。；plan 声称 G2 已完成（commit 9ee0013）但 judges.py 仍是旧契约、无 JudgeResult——执行者若以为契约已就位会踩空；本设计已显式把『补契约』列为步骤0前置。；自研 DSL 文本解析器是脆弱面（中英文冒号混用、@指令拼写、<规则标签> 闭合、空字段/缺参数）——第3期再做且必须配单测覆盖语法错误路径（DslSyntaxError 带行号）；本期可视化结构化 config 绕开这些坑。；NL 规则(LLM) 在 evaluator 内执行时若自建 TraceContext 会与 runner 外层 item scope 嵌套导致渠道/成本归属错乱——设计要求 llm 由 runner 注入、TraceContext 不在 evaluator 内重复 set，复用外层 eval 渠道。；1-5 与 [0,1] 量纲混用：所有 DSL 函数返 1-5，必须统一在 contract 层 /5 归一进 score，否则 mean_score/低分阈值(0.5)/RAGAS 聚合全错位；scale 字段仅作 UI 显示，存储恒 [0,1]。；judge_config 是无 schema 的 JSON 黑盒（复用 EvalTemplate.config 同款）——前端结构化配置与后端解析需契约对齐，建议在 schemas 里给 judge_config 内部结构(dsl_text/visual_config/criteria)留 TypedDict/pydantic 子模型做最小校验，避免运行期 KeyError。；eval_jobs 域若本期接 judge_config 持久化可能引入非必要迁移——建议本期 eval_jobs 不持久化、仅 dataset 即时 run 接 DSL，保持零迁移。

**分期建议**：按 D4 拆两步，且这是评测域【最大/最后】一项，务必排在 judge 契约统一之后：

【步骤0 + 本期（第2期）做】——JudgeResult 契约补齐（plan §G line 237 承诺但实测未落地，是 DSL 的硬地基，不补则 DSL 没有挂载点）+ DSL 可视化逐字段配置（结构化 config → build_spec_from_visual_config → DslSpec → evaluator + functions），覆盖 plan line 250 说的「多数 JSON 逐字段评分场景」，无需用户写 DSL 文本。functions.py 全部内置函数 + 聚合 + 格式限制 + NL 规则(LLM) 本期就要做齐（evaluator 复用）。前端出模式卡片 + 可视化面板 + field_scores 渲染。

【第3期后置】——DSL 文本解析器 parser.py(parse_dsl) 作为「高级出口」：首行 # DSL / 字段:函数:参数 / @指令 / <规则标签> 块。理由：① 文本 DSL 是少数高级用户需求，可视化面板已覆盖 80%；② parser 与可视化面板收敛到同一 DslSpec/evaluator，地基本期已建好，第3期只补「文本→DslSpec」一个入口 + 前端 DSL 文本框(可复用第2期已引入的 json-editor/Monaco 做语法高亮+行级错误条)，增量小、风险隔离。

复杂度评估：契约改造(中，触碰 runner 热路径，要保旧 judge 向后兼容)+ DSL 解析(高，自研小语言要处理中英冒号/作用域/标签块/行号错误)+ 函数库(中，8 个内置函数 + LLM 规则)+ 聚合(低)+ 前端可视化面板(中)。整体 L，建议本期只吃「契约 + 可视化」，把自研文本 parser 这块最硬的留第3期，符合 plan 已定决策 D4 与「不做清单 line 391 DSL 文本编辑后置」。

---

## 实现批次 plan（critic 整合）

**共同基础**：judge-contract-multimode（area 1）与 eval-scoring-dsl 的"步骤0"（area 7）是同一块地基：在 datasets/ 里建 JudgeResult 统一契约 + runner.py 评分热路径收口。这块必须最先做，且这两个 area 重叠/冲突，必须合并成一项串行执行，不能并行。

【已核实的事实，纠正设计前提】
1. judges.py 仍是旧契约（llm_judge 死返 0.5，无 JudgeResult），plan 声称的 G2 契约升级（commit 9ee0013）实测未落地。area-7 的判断正确，area-1 "runner 已部分超前契约"的描述只对一半：runner.py:133-139 确实有 llm_judge 内联特判救活，但 JudgeResult 类型/全契约不存在。
2. DatasetItem 没有 reference_output 列（只有 DatasetRunItem:135 有）。GSB 参照源必须新加 dataset_items.reference_output 列——area-1 迁移计划里已含此列（正确），但 area-2 前端"DatasetItem 侧需 backend 确认"是真未确认项，现已确认=不存在、需建列。
3. 迁移链当前是线性单 head：p26_g01 → p27_a01（newapi，已在 main 提交）。不存在 area-1 假设的"p27_a01 与 p26_g01 两 head 并存"——只有 p27_a01 一个 head。
4. eval_jobs 模型只有 alert_config(JSON)，无 judge_config 列。
5. p27_a01 只动 models（model_def）表，与 datasets/eval_jobs 表零数据交集——新评测迁移与 newapi 无数据冲突，唯一争议是 down_revision 该挂谁。

因此地基 = 「JudgeResult 契约 + judge_config 透传链 + dataset_items.reference_output 迁移 + runner 收口」，这是 GSB / DSL / 配置面板 / 1-5 量纲四者共同依赖的唯一真相源。

### 批次 1 — 评测契约地基（合并 area-1 + area-7 步骤0，单线串行）　[serial（这两项改同一组后端文件，必须当一项做，不可并行）]　areas=['judge-contract-multimode', 'eval-scoring-dsl(仅步骤0 JudgeResult 契约部分)']
area-1 与 area-7 都要在 datasets/ 建 JudgeResult 契约并改 runner.py 评分热路径——这是冲突而非两个独立任务。必须合并为一项：① 定 JudgeResult{score,scale,reason,field_scores}（内部恒 [0,1]，scale 仅 UI 标记）；② runner.py:102-167 去掉 llm_judge 内联特判，统一走 judge_fn 分发并落 field_scores；③ schemas.py DatasetRunRequest 加 judge_config 透传；④ 新迁移 p27_g02：加 dataset_items.reference_output(JSON nullable) + eval_jobs.judge_config(JSON nullable)，down_revision 必须挂 p27_a01（保持线性单 head，不要按 area-1 原稿挂 p26_g01 制造无谓两 head）；⑤ 旧三函数（exact/contains/llm_judge）用适配器包成 JudgeResult 保向后兼容。落地后立即跑现有 dataset run e2e 回归（这是热路径，向后兼容是硬约束）。本批不做 GSB/DSL 具体 judge，只把挂载点和透传链通好。

### 批次 2 — 新 judge 模式（GSB + llm_score）+ DSL evaluator/functions　[serial（仍触碰 runner/judges 注册表 + schemas，与批次1 同文件域，接续做）]　areas=['judge-contract-multimode(llm_score+gsb judge 落地)', 'eval-scoring-dsl(functions.py+evaluator.py+可视化config 入口)']
契约就位后挂具体 judge：llm_score（criteria→1-5 归一）、gsb（reference→G/S/B→{1,0.5,0}）、dsl 的 functions.py（8 内置函数）+ evaluator.py（解析→逐字段→NL 规则交 LLM→聚合→/5 归一）+ build_spec_from_visual_config（结构化入口，非文本 parser）。LLM 评分逻辑留 runner/evaluator（编排层可依赖 integrations），judges.py 只出 prompt 构造 + 解析纯函数——守住 import-linter 两契约 GREEN。dsl 文本 parser.py 本批不做（后置批次5）。本批仍改 judges.py 注册表/runner 分发/schemas judge_config 子结构，与批次1 同一文件域，故接续串行而非并行。

### 批次 3 — 评测域前端（配置面板 + 1-5 量纲 + field_scores 渲染）　[parallel 受限：两者都改 eval-job-form-modal.tsx，需对该文件串行；其余文件可并行]　areas=['eval-judge-config-frontend', 'eval-scale-ui-1to5']
批次1/2 把后端 judge_config + JudgeResult.scale + 各 judge 落地后，前端才有真东西可配/可展示（否则空架子）。eval-judge-config-frontend 出 JudgeConfigPanel（模式卡片替 Select + criteria/model/gsb 参照源 + DSL 可视化逐字段构建器，DSL 卡按 judges 端点可用集自适应置灰）；eval-scale-ui-1to5 出 score.ts scale 形参 + judge-scale.ts 派生（纯前端零后端依赖，可最先并行起步）。冲突点：两者都改 eval-job-form-modal.tsx（前者改 judge Select→Panel，后者改 JUDGE_META 量纲文案）——必须串行编辑此文件（建议先做 config-frontend 的 Panel 抽取，再做 scale 的文案对齐）。run-detail-drawer.tsx 也被 area-7 的 field_scores 渲染 + area-3 的 1-5 映射同时碰，需协调。

### 批次 4 — 独立增强（H1 playground + H3 优化落库版本链）　[parallel（两者文件域不交叉：H1 在 playground 域，H3 在 datasets optimizer/run 域）]　areas=['H1-playground-vars-rewrite', 'H3-version-lineage-and-optimization-persistence']
这两项 depends_on 为空，与 judge 契约链零耦合，可与批次2/3 并行甚至更早起步。H1（{{var}} 抽取填值 + 基于回答改写 prompt）纯前端 + 一个 playground/prompt/rewrite 非流式端点，复用已就位的 channel='eval' 范式。H3（优化产出落 DatasetRun 3 列 + parent_run_id 自引用版本链 + apply-optimized 建新 run + compare 复用）复用现有 runner/compare-matrix，零引擎改造。H3 新迁移 p27_h01 down_revision 挂 p27_a01——但若批次1 的 p27_g02 先合并，p27_h01 需改挂 p27_g02（保持线性，避免两 head）。这是批次间迁移链串行约束，落地前重新确认 alembic heads。H1/H3 之间无文件交叉，可真并行。

### 批次 5 — 后置第3期（DSL 文本 parser + H2 电子表格）　[parallel（DSL parser 在后端 datasets/dsl，H2 在前端 datasets 组件 + create/delete 端点，不交叉）]　areas=['eval-scoring-dsl(parser.py DSL 文本解析器)', 'H2 评测集电子表格编辑']
两者 plan 均明确后置第3期。DSL 文本 parser（首行 # DSL / 字段:函数:参数 / @指令 / <规则标签> 块，中英冒号/作用域/行号错误）是自研小语言、最脆弱面，且批次2 的可视化 config 已覆盖 80% JSON 逐字段场景，parser 与可视化收敛同一 DslSpec/evaluator，只补「文本→DslSpec」一个入口+前端文本框。H2 电子表格（动态列推断 + 行内编辑 + create/delete 端点 + 维护 item_count）是 PromptPilot 级差异化锦上，B 全字段抽屉 + C Excel 导入已让编辑闭环可用，且其 GSB「模型回答拆 A/B 列+分数列」依赖批次2 的 gsb judge 落地。两者纯增量、风险隔离、与 newapi 零交叉，最后做。

**文件冲突点**：
- 【runner.py】批次1（去 llm_judge 内联特判+统一 JudgeResult 分发+落 field_scores+扩 judge 校验 :57）与批次2（注册 gsb/llm_score/dsl judge）同改此热路径——必须合并为单线串行，绝不两人并行改 :102-167。area-1 与 area-7 都声称要改 runner，是同一处冲突。
- 【judges.py】批次1（旧三函数适配器包 JudgeResult + list_judges 加 dsl/gsb）与批次2（新 judge 注册）同改——串行。area-1 把 LLM 评分留 runner、judges 只出纯函数；area-7 也同此分层结论，无矛盾，但落地需统一由一人收口避免双实现分叉。
- 【schemas.py DatasetRunRequest】批次1 加 judge_config 字段，批次2 给 judge_config 内部结构（dsl_text/criteria/visual_config）加 TypedDict/pydantic 子模型最小校验——同字段两次改，批次1 先建 dict|None 黑盒位，批次2 收窄子结构，串行。
- 【迁移 down_revision】三处设计各执一词且都有错：area-1 说挂 p26_g01（错，会与 p27_a01 制造无谓两 head）；area-5(H3) 说挂 p27_a01（对，线性）；area-7 说挂当前 head 避开 p27_a01（含糊）。已核实当前唯一 head = p27_a01。结论：批次1 的 p27_g02 挂 p27_a01；批次4 的 p27_h01 挂 p27_g02（按批次顺序线性递进），落地前每次 alembic heads 复查。绝不碰 p27_a01 文件本身。
- 【eval-job-form-modal.tsx】批次3 内 eval-judge-config-frontend（judge Select→JudgeConfigPanel + judge_config state 透传）与 eval-scale-ui-1to5（JUDGE_META 量纲文案对齐 1-5）同改——批次内串行编辑此文件，先 Panel 抽取再文案对齐。
- 【run-detail-drawer.tsx】批次2(area-7 field_scores 逐字段渲染 :393-404 旁) 与批次3(area-3 :148/:338/:286/:314-317 的 1-5 映射) 同改——协调单元格分数 chip 既要按 scale 映射又要展示 field_scores，需同一人收口此组件或明确分区。
- 【api.py(datasets)】批次1(run_dataset 透传 judge_config) 与批次5(H2 加 create_item/delete_item 端点)、批次4(H3 加 apply-optimized 端点) 多批在同文件追加 handler——纯追加无逻辑冲突，但需按批次顺序 append 避免 git 行冲突。
- 【eval_jobs/service.py + schemas.py】批次1 给周期任务透传 judge_config（_validate_judge :322 随 JUDGES 扩容放行）。注意：area-7 建议 eval_jobs 本期不持久化 judge_config 以求零迁移，但 area-1 要给 eval_jobs 加 judge_config 列——二者矛盾。决议：既然 dataset_items.reference_output 迁移已不可免，顺手在同一支 p27_g02 加 eval_jobs.judge_config 列（边际成本零），采纳 area-1 方案，eval_jobs 一步到位持久化，推翻 area-7 的「eval_jobs 不接」保守建议。

**遗漏/矛盾**：
- 【矛盾·已核实】area-1(judge-contract-multimode) current_state 暗示「runner 已部分超前于契约」「llm_judge 已被 runner 旁路救活」，读起来像契约半就位；area-7 直接点破 judges.py 仍旧契约、JudgeResult 不存在、plan 声称的 commit 9ee0013/G2 未落地。实测以 area-7 为准：契约从零建。执行者若信 area-1 措辞会踩空。
- 【遗漏·已核实】area-2(前端) 说「GSB reference_output 在 DatasetItem 侧是否已有列需 backend 确认」——现确认：DatasetItem 无此列（仅 DatasetRunItem 有），必须新建。area-1 迁移已含 dataset_items.reference_output（正确），但两份设计未交叉锁死此事，需在批次1 显式建列后批次3 前端 GSB 参照源选项才可用。
- 【矛盾】area-1 与 area-7 对 dsl judge 本期范围表述不同：area-1 说 dsl 本期「只预留 key + try-import 透传桩」，真解析器全后置；area-7 说本期就做 functions.py 全部内置函数 + evaluator + 可视化 config 入口，只把文本 parser 后置。采纳 area-7（更激进但合理）：本期(批次2) 做 DSL 可视化+evaluator+functions，文本 parser 后置(批次5)。area-1 的「纯桩」过于保守，会让 DSL 卡本期完全不可用。
- 【遗漏】area-2 提议后端补 GET /v1/admin/datasets/judge-meta 返各模式可配字段 schema + DSL 函数清单，供前端渲染避免硬编码后端枚举；area-1/area-7 均未规划此端点。这是强契约耦合点（DSL 函数名前后端必须一一对齐），建议批次2 后端补 judge-meta 端点，批次3 前端据此渲染——否则前端硬编码 DSL 函数集会静默漂移。
- 【量纲一致性·跨 3 个 area 的隐患】area-1/area-3/area-7 都反复强调内部恒 [0,1]、1-5 只是 UI 皮肤、原档入 field_scores——三者结论一致(D3)，但分散在三处实现。批次1 必须把「/5 或 (n-1)/4 归一」收口在 JudgeResult 构造/contract 单点，禁止 runner、evaluator、前端各算一次，否则 mean_score/低分阈值 0.5/RAGAS/score_distribution 桶全错位。这是最大的跨 area 一致性风险。
- 【gsb None 跳过的 UI 表达】area-1 指出 gsb reference 缺失返 score=None 会让该 item 不计入 mean_score（runner :170），需 UI/summary 标「无参照样本已跳过」。批次3 前端设计(area-2/area-3)未明确接此提示——补：summary 加 skipped_count 或前端按 score===null 标注，避免误读通过率。
- 【H2 与 plan §H2 文案出入】area-4(H2) 自陈：plan §H2 提模型回答拆 A/B 列+分数列，但 H2 本设计只做样本列（{{var}}+理想回答+meta），模型回答/分数属运行态非样本态、依赖批次2 的 gsb judge。这是设计主动收窄，合理，但落地时需与 plan 对齐预期，避免被当作未完成。
- 【未覆盖 plan 要点】七份设计未见任何一份处理「评测结果导出 Excel(C 模块/SheetJS)」与 1-5 量纲的交互——area-3 提到「导出走原始值不走 display 字符串」「列头标注(1-5)」，但 C 模块导出本身不在这 7 个 area 内。若 C 模块已落地，批次3 需确认导出仍写 [0,1] 原始值、不被 1-5 display 污染。

**总体推荐**：
推荐执行顺序与取舍：

【最先做·不可绕】批次1 评测契约地基（合并 area-1 + area-7 步骤0）。这是 GSB/DSL/配置面板/1-5 量纲四者唯一共同地基，且 area-1 与 area-7 在此重叠冲突，必须合并成单项串行。务必：JudgeResult 归一逻辑收口单点（[0,1] 恒定）；新迁移 p27_g02 加 dataset_items.reference_output + eval_jobs.judge_config，down_revision 挂 p27_a01 保线性单 head；旧三函数适配器保向后兼容；落地即跑 dataset run e2e 回归。绝不碰 p27_a01/model_def/factory/providers（newapi 并行工作）。

【高价值低风险·可并行早起步】H1(批次4) 与 eval-scale-ui-1to5 的纯前端基建(批次3 score.ts/judge-scale.ts 骨架)。两者 depends_on 空或弱、零迁移、与 newapi 零交叉，可在批次1 进行时并行铺基建（scale 形参先支持 exact/contains/llm_judge 三态，新模式分支随批次2 补）。H3(批次4) 同属低风险（复用 runner/compare，仅新迁移 p27_h01 需挂批次1 之后的 head）。

【中段·依赖地基】批次2(新 judge 模式 + DSL evaluator/functions) → 批次3(配置面板 + 量纲接线 + field_scores 渲染)。批次2 必须在批次1 后串行（同改 runner/judges/schemas）；批次3 待批次2 后端 judge 就位才有真东西可配，且批次3 内两 area 串行编辑 eval-job-form-modal.tsx。建议批次2 顺手补 GET judge-meta 端点，消除前后端 DSL 函数枚举漂移。

【建议彻底后置第3期】批次5：DSL 文本 parser（自研小语言、最脆弱面，必须单测覆盖 DslSyntaxError 行号路径）+ H2 电子表格编辑（差异化锦上，非可用性底线，且其模型回答列依赖 gsb judge）。两者纯增量、风险隔离，最后做。

【取舍裁决】① 采纳 area-7 的激进 DSL 范围（本期做可视化+evaluator+functions，仅文本 parser 后置），推翻 area-1 的「纯桩」保守；② 采纳 area-1 的 eval_jobs.judge_config 持久化（边际成本零，一支迁移搞定），推翻 area-7 的「eval_jobs 本期不接」；③ 三处迁移 down_revision 统一线性递进：p27_g02→p27_a01、p27_h01→p27_g02，每批落地前 alembic heads 复查；④ 量纲归一收口单点是最高优先级一致性约束，三个 area 不得各算一次。

【最大风险点】批次1 的契约改造触碰 runner 评分热路径且 eval_jobs 复用同一 judge——向后兼容是硬约束，必须适配器包旧三函数 + 改造后 e2e 回归，否则击穿存量 run。area-1 的 current_state 措辞会误导执行者以为契约半就位，须以实测（judges.py 仍旧契约）为准。
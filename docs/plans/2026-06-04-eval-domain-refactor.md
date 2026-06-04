# Chameleon 评测域重构计划

> 从「能跑数据集打分」升级到「好用、可分析、可调试的 Prompt 工程工作台」
> 借鉴对象：火山引擎 PromptPilot（调试→批量→智能优化 三阶段闭环）
> 日期：2026-06-04 · 范围：`datasets` 域 + `playground` 域 + judge 体系 + Trace 渠道

---

## 执行进度（`/loop` SSOT —— 每次迭代读这张表找第一个 ⬜）

| # | 模块 | 优先级·量 | 状态 | commit |
|---|------|-----------|------|--------|
| 1 | A 基础体验汉化 + 选择器化 | P0·S | ✅ | 3599e20 |
| 2 | D 评测流量入 eval 渠道 | P0·S | ✅ | 3599e20 |
| 3 | B 专业 JSON + 全字段样本编辑 | P0·M | ✅ | 24a0721 |
| 4 | E 运行详情重做 | P0·M | ✅ | 604e1e5 |
| 5 | C Excel 导入导出 + 模板 | P1·S–M | ✅ | 10f6080 |
| 6 | F 运行 tab 分析统计 | P1·M | ✅ | 33842d3 |
| 7 | G judge 第一刀（契约 + AI 评分救活 + 迁移 + 理由） | P1·M | ✅ | 607b8ad |
| 8 | H1 playground 存为评测样本（{{var}}/改写留后续） | P1·M | ✅ | dc0f020 |
| 9 | H2 AI 扩样（电子表格编辑留后续） | P2·M | ✅ | 5321239 |
| 10 | H3 智能优化 + 报告 + diff | P2·L | ⬜ | |
| 11 | G2 judge 多模式（GSB / DSL 解析器 / 1-5 量纲 / 评分配置面板） | P1·L | ⬜ | |

> 状态：⬜ 待做 · 🔄 进行中 · ✅ 完成 · ⚠️ 阻塞。顺序即依赖序（D 先于 G/H，B 先于 H，G 契约一次到位）。

## ⚠️ 阻塞

（`/loop` 遇验证失败时在此记录「模块 / 失败项 / 诊断」并停止；为空表示无阻塞。）

---

## 一、设计原则 + 总体目标

### 现状一句话定性

我们现在做的是「**先有数据集 → 跑 run → 出 mean_score**」的单向跑批工具；PromptPilot 做的是「**改 Prompt 的工作台**」。骨架我们不弱（`metrics / judge / runs / bulk-import / sample-from-logs / run-compare / 分数分布桶 / 低分下钻` 全有），缺的是**面向 Prompt 工程师的产品化闭环**：变量表格电子表格、GSB 对比、AI 扩样、可配置评分、一键优化重写 + 报告、版本 diff 追溯，以及最基础的**可用性**（汉化、选择器化、专业 JSON 编辑器、长文本可读）。

### 五条设计原则

1. **可用性优先于能力堆叠**。用户第一痛点是「英文术语看不懂、JSON 难编辑、长输出看不全、关联字段靠手输」——这些是 P0，先把「能用」做扎实，再谈「智能」。
2. **复用既有资产，不另起炉灶**。`agent-picker` 模式 → `model-picker`；`DataTable` → 运行/样本表；`BaseLLM` 切面 + `channel` 体系 → eval 渠道；`json-cell` → 升级成 Monaco；`MetricDistribution.low_score_item_ids` → 低分下钻已具雏形。
3. **数据模型尽量不破坏，加列不改列**。`input_payload`（变量列）/ `expected_output`（理想回答）/ `MetricSpec`（评分）/ `prompt_override`（优化产出落点）已经对得上 PromptPilot 的列结构，主要是**加字段 + 加端点**，不是推倒。
4. **judge 契约统一升级一次，后续模式都挂上去**。把 `float | None` 升级为 `JudgeResult{score, scale, reason, field_scores}`，GSB / AI 评分 / DSL / 1-5 全部基于同一契约，避免多套并行。
5. **AI 能力（生成变量 / AI 评分 / 智能优化）默认走系统模型 + 新 eval 渠道**，成本进 Trace、可统计、可关闭。不引入隐性 token 黑洞。

### 总体目标（验收口径）

- 非工程师能在不看文档的情况下，从「调用日志采样 → 编辑样本 → 跑评测 → 看分析 → 下钻低分」全流程走通（汉化 + 选择器 + 富展示）。
- Prompt 工程师能「playground 单条调好 → 存为种子 → AI 扩样 → 跑批 → 一键优化出新 Prompt + 报告 + 前后 diff」闭环。
- 所有评测期间的 LLM 调用进 Trace + 成本统计（`channel='eval'`）。
- judge 从 3 个二值函数升级为「1-5 量纲 / GSB / AI 带理由 / DSL 多字段」多模式可配置。

---

## 二、关键现状锚点（落地参照，避免重复踩点）

**后端 `backend/chameleon-system/src/chameleon/system/datasets/`**
- `judges.py` — 仅 3 函数：`exact_match` / `contains`（二值 1.0/0.0）、`llm_judge`（**死返 0.5**，注释「P19 完善」至今未接）。契约 `async def judge(expected, actual) -> float | None`，单字段、无参数、无理由。
- `runner.py:110` — `score = await judge_fn(item.expected_output, actual)`，judge 注入点在 `runner.py:93`；LLM 调用在 `_invoke_for_item`（`get_llm(model_override)` + `ainvoke`），agent 路径 `_invoke_via_agent`。**此处是 eval 渠道埋点的天然切口**。
- `schemas.py` — `DatasetRunItemRow{score, actual_output, error, duration_ms}`（无 reference / reason / field_scores）；`MetricDistribution.low_score_item_ids`（低分下钻已具雏形，**我们这点反而领先 PromptPilot**）；`DatasetRunDetail.prompt_override`（优化产出落点已在）。
- `template_scoring.py` — 独立 RAGAS 路径（faithfulness / answer_relevance / context_precision / context_recall），返 [0,1]，红线禁改 weight/定义。
- `pii.py` — mask / drop / keep 策略，采样和导入复用。

**前端 `frontend/src/system/datasets/`**
- `components/{bulk-import-modal, sample-from-logs-modal, run-compare-matrix, run-detail-drawer, eval-template-form-modal}.tsx`
- `pages/{datasets-page, dataset-detail-page, eval-templates-page}.tsx`
- `types/{dataset, eval-template}.ts` · `services/{dataset, eval-template}.ts`
- 量纲：全栈 [0,1]（`Score.value` float、`mean_score` 平均）。PromptPilot 是 1-5。

**Playground `frontend/src/system/playground/`** — `components/{composer, message-thread, param-panel, file-attach-button}.tsx`。**无变量 `{{var}}` 抽取/填值、无「基于回答改写」、无「存为评测样本」**——这三个是升级成调优工作台的最小集。

**可复用资产（确认存在）**
- `frontend/src/core/components/common/agent-picker.tsx` — 无限滚动 + 类别栏 + 搜索；`onChange(agent_key)`。**直接照抄成 model-picker**。
- `frontend/src/core/components/table/data-table.tsx` — 通用表格。
- `frontend/src/core/components/ui/json-cell.tsx` — 折叠 JSON 单元格（**只读**，需升级 Monaco 编辑）。
- `GET /v1/admin/models?kind=chat`（`backend/.../system/models/api.py:77`）— **model-picker 现成数据源**，无需新建端点。
- `channel` 字段已在 `api_key.py:108`，`channel='playground'` 已贯穿 `playground/service.py` + `graphs/runner.py` → **新增 `'eval'` 渠道是加值不是改架构**。
- `chameleon-integrations/.../observe/{aspect, llm_recorder, graph_spans}.py` — Trace 切面，eval 渠道挂这里。

---

## 三、模块化重构计划

> 每模块标注：**现状痛点 / 目标 / 关键改动（前端·后端·数据模型）/ 借鉴 PromptPilot 哪个点 / 优先级 / 工作量**。
> 优先级：P0 必做（可用性底线） · P1 应做（产品化闭环） · P2 增强（差异化锦上）。工作量：S（≤2d）· M（3–5d）· L（>1w）。

---

### 模块 A — 基础体验：汉化 + 选择器化

**现状痛点**
- 「从调用日志采样」弹窗全是英文术语（`agent_key / app_id / PII / mask / drop / keep / expected_output`），PII 策略不知所云。
- 「手工导入」弹窗同样英文术语。
- 系统关联字段（`app_id / agent_key / model`）靠手输，易错、不可发现。

**目标**：弹窗全中文 + 行内说明 + tooltip；所有关联字段「选择」而非手输。

**关键改动**
- **前端**
  - `sample-from-logs-modal.tsx` / `bulk-import-modal.tsx` 全量汉化：字段中文标签 + 行内 helper 文案 + `Tooltip` 解释（PII 策略三态用人话：脱敏=替换邮箱/手机号占位符（默认）/ 丢弃=含敏感信息整条跳过 / 保留=原样，明确无敏感信息时用）。
  - **新建 `core/components/common/model-picker.tsx`**：照抄 `agent-picker` 结构（Popover + 搜索 + 列表），数据源 `GET /v1/admin/models?kind=chat`，`onChange(model_code)`。类别栏可按 `provider` 分组。
  - `app_id` 字段：复用应用选择器（若无则补一个轻量 select，走应用列表端点）。
  - `agent_key`：直接用现有 `agent-picker`。
  - 替换所有手输 model/agent/app 的 `<Input>`。
- **后端**：无（`/v1/admin/models` 已存在）。
- **数据模型**：无。

**借鉴自 PromptPilot**：「填系统关联字段一律选择」——PromptPilot 模型走右上角下拉选，变量旁按钮填值，没有裸手输。

**优先级 P0 · 工作量 S**（model-picker 是主要工作量，汉化是文案活）

---

### 模块 B — 专业 JSON 编辑器 + 全字段样本编辑

**现状痛点**
- 样本只能编辑「预期输出」，不能编辑「输入 / meta」。
- 所有 JSON 编辑是裸 textarea / 折叠只读 `json-cell`，无语法高亮、无校验、无格式化。

**目标**：样本可编辑 `input_payload` / `expected_output` / `meta` 全字段；所有 JSON 编辑换成 Monaco/CodeMirror（高亮 + 校验 + 格式化 + 错误提示）。

**关键改动**
- **前端**
  - 引入 `@monaco-editor/react`（或 CodeMirror 6，体积更小——见开放问题 Q1）。**新建 `core/components/ui/json-editor.tsx`** 封装：`value / onChange / schema?(可选 JSON Schema 校验) / readOnly`，内置「格式化」按钮 + 实时语法错误条。
  - `json-cell.tsx`：保留只读展开（表格展示用），编辑场景一律切 `json-editor`。
  - 新建 / 改造**样本编辑抽屉 `dataset-item-editor-drawer.tsx`**：三段式（输入变量 / 理想回答 / meta），各自一个 Monaco 面板。
- **后端**
  - `UpdateItemRequest` 扩 `input_payload`（schemas.py:84 当前只有 `expected_output / meta`）。
  - service 层 update 支持三字段；保留 PII 校验（编辑后若引入敏感信息按策略处理）。
- **数据模型**：无（字段都在 `DatasetItem`）。

**借鉴自 PromptPilot**：变量表格每个 `{{var}}` 是一列可编辑、理想回答可改写——全字段可编辑是表格化交互的前提。

**优先级 P0 · 工作量 M**

---

### 模块 C — 导入导出：Excel + 模板下载

**现状痛点**：只支持 JSONL/JSON 粘贴；术语英文；无 Excel；无模板。

**目标**：支持 Excel/CSV 导入 + 导出；导入前可下载列模板；汉化。

**关键改动**
- **前端**
  - `bulk-import-modal.tsx`：加「上传 Excel/CSV」入口 + 「下载模板」按钮（模板列 = 各 `{{var}}` 列 + `理想回答` + `meta`）。解析建议放前端（见开放问题 Q2），用 `xlsx`（SheetJS）解析成 `BulkImportItem[]` 再走现有 `/bulk-import` 端点。
  - 数据集详情加「导出」：当前样本 → Excel/CSV 下载。
- **后端**
  - 若解析放后端：新增 `POST /datasets/{id}/import-file`（multipart），后端用 `openpyxl` 解析；否则复用现有 bulk-import。
  - 导出端点 `GET /datasets/{id}/export?format=xlsx|csv`（流式返文件）。
- **数据模型**：无。

**借鉴自 PromptPilot**：评测集 Excel/CSV 导入导出 + 模板，是批量阶段标配。

**优先级 P1 · 工作量 S**（前端解析）/ **M**（后端解析 + 导出）

---

### 模块 D — 评测流量入 Trace（新增 `eval` 渠道）

**现状痛点**：评测期间调大模型（judge LLM、被测 LLM、未来 AI 扩样/AI 评分/智能优化）的流量**不进 Trace、不计成本**。

**目标**：所有评测 LLM 调用绑定 `channel='eval'`，进 call_logs / Score / 成本统计，可在可观测域筛出「评测产生的流量」。

**关键改动**
- **后端**
  - `runner.py` 的 `_invoke_for_item` / `_invoke_via_agent`：构造 `InvokeContext` / LLM 调用时透传 `channel='eval'`（参照 `playground/service.py:342` 的 `channel="playground"` 写法）。
  - judge LLM（模块 G 的 `llm_score` / AI 评分）、AI 扩样（模块 H）、智能优化（模块 H）的 LLM 调用同样打 `channel='eval'`。
  - 在 `channel` 取值约定处登记 `'eval'`（当前是 `String(16)` 自由文本，无枚举约束，**加一个常量集中管理避免散落字符串**——建议 `data/constants/channels.py`）。
  - 复用 `observe` 切面（`BaseLLM` 已收口），渠道作为 trace 标签透传，**不新增切面**。
- **前端**：可观测域筛选条件加 `eval` 选项（小改）。
- **数据模型**：无 schema 变更（`channel` 字段已在）。

**借鉴自 PromptPilot**：智能优化前配「效果与成本」参数——评测/优化的算力消耗是一等公民，必须可观测可计费。

**优先级 P0 · 工作量 S**（是新功能 G/H 进 Trace 的前置，先铺渠道）

---

### 模块 E — 运行详情抽屉重做

**现状痛点**（`run-detail-drawer.tsx`）
- 分数分布只有一个空直方图。
- 样本明细太简单；AI 输出很长只能单行横向滑动看不全。
- 功能单调。

**目标**：分数分布可读（实心柱 + 区间 + 低分高亮）；样本明细富展示；长文本可完整查看（折叠/展开/弹层/diff）。

**关键改动**
- **前端**
  - **分数分布**：用 `MetricDistribution.buckets` 渲染实心直方图（已有数据，只是没画好），低分桶高亮 + 点击桶 → 过滤到该桶样本。多指标分 tab/分组。
  - **样本明细表**：用 `DataTable`，列 = `输入预览 / 理想回答 / 模型回答 / 分数 / 耗时 / 错误`；长文本用「展开行」或「点击开 Monaco 只读弹层」完整看，不再横向滑动。
  - **三栏对比视图**（理想回答 / 模型回答 / 评分理由）；GSB 模式（模块 G）下展示 参照回答 vs 模型回答 + G/S/B 标。
  - 低分样本一键「加入下一轮调试」/「跳 playground 调」（衔接模块 H）。
- **后端**
  - 运行详情返回需带 `expected_output` / `actual_output` / `score_reason`（模块 G 加）/ `reference_output`（GSB）——`DatasetRunItemRow` 扩字段。
- **数据模型**：`DatasetRunItem` 加 `score_reason` / `field_scores` / `reference_output`（与模块 G 合并迁移）。

**借鉴自 PromptPilot**：评测集表格「模型回答 / 评分 / 评分理由」列 + 低分下钻反向修正。

**优先级 P0 · 工作量 M**

---

### 模块 F — 运行 Tab 分析统计

**现状痛点**：数据集详情的「运行」tab 太简单，只是 run 列表 + mean_score。

**目标**：引入分析统计 + 高级交互（趋势、对比、指标聚合、筛选排序）。

**关键改动**
- **前端**
  - run 列表升级 `DataTable`：列 `名称 / 模型 / judge / 状态 / mean / 通过率 / 耗时 / 时间`，可排序筛选。
  - **运行趋势**：多次 run 的 `mean_score` 折线（`DatasetItem.score_trend` 已有雏形）+ 各指标趋势。
  - **多 run 对比**：复用 `run-compare-matrix.tsx`（item-by-item 横向比已有），补「胜率 / 提升项 / 退步项」汇总 + 高亮 diff。
  - 概览卡：本数据集 总样本 / 总运行 / 最佳 run / 最近趋势。
- **后端**
  - 趋势聚合端点 `GET /datasets/{id}/run-trend`（或在 list 里返）。
  - compare 端点补 win/tie/loss 汇总（现 `CompareRunsResult` 只有 rows）。
- **数据模型**：无。

**借鉴自 PromptPilot**：PromptPilot 管理里按任务统一管理迭代版本 + 版本对比追溯。

**优先级 P1 · 工作量 M**

---

### 模块 G — judge 体系升级（多模式 / GSB / AI 评分 / DSL）

**现状痛点**：3 个 judge（exact/contains 二值、llm_judge 死返 0.5）；量纲 [0,1]；单字段、无参数、无理由、无 GSB、无 DSL、无 AI 评分。

**目标**：judge 升级为「多模式可配置」：1-5 量纲、GSB 对比、AI 带理由评分、按字段 DSL。

**关键改动**
- **后端 — judge 契约升级（一次性，统一基座）**
  - `JudgeResult{ score: float, scale: '0-1' | '1-5', reason: str | None, field_scores: dict | None }` 取代裸 `float | None`。
  - `judge_fn` 签名升级为 `async def judge(expected, actual, *, reference=None, config=None) -> JudgeResult | None`；`runner.py:110` 改造适配（向后兼容旧三函数：包成 `JudgeResult`）。
  - 新增 judge 类型：
    - `llm_score`：接 `criteria`（用户写多行评分细则）→ LLM 输出 **1-5 + reason**（这是把死掉的 `llm_judge` 救活）。
    - `gsb`：对 `reference_output` 做 **G/S/B** 三态（无金标准答案时用，评相对优劣）。
    - `dsl`：解析评分 DSL（见下）按字段评分 + 聚合。
    - 保留 `exact_match` / `contains` / RAGAS 模板路径。
  - **量纲策略**：内部统一 [0,1] 存储，UI 层映射 1-5 显示（PromptPilot 是 1-5；我们 RAGAS 是 [0,1]）；或 `JudgeResult.scale` 标量纲、聚合时归一。**取舍见开放问题 Q3**。
  - **评分 DSL 解析器**（`datasets/dsl.py`）：
    - 语法：首行 `# DSL` → 每行 `字段名：函数[：参数]` → `@聚合方式` / `@格式限制` / `@全部字段` / `@单个字段`。
    - 内置函数（量纲 1-5，二值取 5/1）：精确匹配 / 模糊匹配(1-5) / 字数限制 / 格式限制 / 常量等于 / 常量不等于 / 精确存在于 / 精确全包括 / 自然语言规则(LLM, 1-5 + reason)。
    - 聚合：min/max/mean(默认)/median/mode；格式：字符串/JSON/XML；`@格式限制` 缺失或不合规整条记最低分。
    - `<规则标签>...</规则标签>` 多行自然语言规则块交 LLM 执行。
    - **是否完整自研 DSL 见开放问题 Q4**——建议先做「JSON 逐字段配函数 + 聚合」的**可视化配置**（无需用户写 DSL 文本），DSL 文本作为高级出口后置。
- **后端 — AI 评分（few-shot）**
  - 「AI 以种子人工评分为参照」批量打分：把已有人工评分样本当 few-shot 喂 judge LLM。复用 `EvalTemplate.config`（规约允许的 customize 出口）承载 criteria / few-shot 配置。
  - 所有 judge LLM 调用走 `channel='eval'`（模块 D）。
- **前端**
  - judge 选择从裸字符串下拉升级为「模式卡片」：`精确/包含` / `AI 评分(1-5+理由)` / `GSB 对比` / `DSL 多字段`，每种带配置面板。
  - GSB 模式 UI：左模型回答 / 右参照回答 / G·S·B 三按钮（人工）或 AI 自动判。
  - 评分理由展示（run-detail 模块 E 已铺位）。
- **数据模型**
  - `DatasetRunItem` 加 `score_reason` / `field_scores`（JSON）/ `reference_output`（GSB 参照，JSON）。
  - `DatasetItem` 可选加 `reference_output`（GSB 用，区别于 `expected_output` 金标准语义）——或复用 `meta`，见 Q5。
  - `DatasetRunRequest.judge_config`（透传 DSL 文本 / criteria / few-shot 配置）。
  - 一次 Alembic 迁移（与模块 E 合并）。

**借鉴自 PromptPilot**：三模式 + DSL 的整套评分体系（1-5 / GSB / AI 评分理由 / 评分 DSL）。这是评分能力的核心增量。

**优先级 P1 · 工作量 L**（DSL 解析器 + 多模式 judge + 前端配置面板）

---

### 模块 H — 提示词 & 模型调试闭环（借鉴 PromptPilot 三阶段）

**现状痛点**：playground 只能聊；调好的 Prompt 无法沉淀成评测样本；评测出问题无法反向改 Prompt；无「调试→批量→优化」闭环。

**目标**：打通「单条调试 → 存为种子/加入评测集 → AI 扩样 → 跑批 → 一键智能优化出新 Prompt + 报告 + 前后 diff」。

**关键改动**（按子阶段，可独立交付）

**H1 调试阶段（playground 升级为调优工作台）**
- **前端**
  - `composer` / `param-panel` 加 `{{var}}` 抽取：Prompt 里写 `{{name}}` → 自动识别成可填字段，变量旁按钮填值（文本直填）。
  - 「基于模型回答改写」轻量按钮：输入改写需求 → LLM 改 Prompt（区别于 H3 重型智能优化）。
  - 「存为种子 / 加入评测集」按钮：单条 → `DatasetItem`（`input_payload`=变量值，`expected_output`=理想回答）。
  - model-picker（模块 A）选模型。
- **后端**
  - `POST /playground/save-as-sample`（单条 → dataset item），走 `channel='eval'` 不污染 playground 渠道。
  - 「基于回答改写」端点：`POST /prompt/rewrite`（LLM 改写，eval 渠道）。

**H2 批量阶段（AI 扩样）**
- **后端**
  - `POST /datasets/{id}/ai-generate`：输入任务描述 + 种子样本 → LLM **批量生成变量组合**（如批量造候选人简历/JD）扩样。eval 渠道、成本进 Trace。
  - 一键批量跑：现有 run 端点已支持，补「全表运行」入口。
- **前端**
  - 评测集**电子表格编辑**（核心交互）：每个 `{{var}}` 一列 + 理想回答列 + 模型回答列 + 分数列，行内可编。GSB 模式模型回答拆 A/B 列。
  - 「AI 生成样本」按钮 → 调 ai-generate → 填表。

**H3 智能优化阶段（一键重写 Prompt + 报告 + diff）**
- **后端**
  - `POST /datasets/runs/{id}/optimize`：输入 当前 Prompt + 整个评测集（带评分）→ 优化算法（汇总低分样本共性缺陷，复用 `low_score_item_ids`）→ 产出 **新 Prompt 版本 + 优化报告（改了哪些点、为什么改）**。异步（10–15min），落 `DatasetRunDetail.prompt_override`（落点已在）+ 新报告字段。
  - 优化是**多轮 LLM 调用**，全程 `channel='eval'`。
- **前端**
  - 「智能优化」按钮（区别于 H1 轻量改写）→ 异步任务进度 → 产出页：新 Prompt + 优化报告 + **前后 Prompt diff（左右对比 + 高亮改动）**。
  - 版本追溯：每次优化是一个可追溯版本，`run-compare-matrix` 关联「版本→评分变化」。
- **数据模型**
  - 优化产出：新增 `prompt_optimization` 表或在 run 上加 `optimization_report`（JSON）+ `optimized_prompt`（text）+ `parent_run_id`（版本链）。
  - `DatasetRun` 加 `parent_run_id` 做版本追溯链。

**借鉴自 PromptPilot**：整套「调试→批量→智能优化」三阶段闭环 + 单条「添加到评测集」流转 + 一键智能优化报告 + 版本 diff。这是从「评测平台」跨到「Prompt 优化平台」的核心。

**优先级**：H1 **P1·M** / H2 **P2·M** / H3 **P2·L**

---

## 四、复用资产清单（明确「抄哪个」）

| 新能力 | 复用资产 | 复用方式 |
|--------|---------|---------|
| model-picker | `core/components/common/agent-picker.tsx` | 照抄结构，数据源换 `GET /v1/admin/models?kind=chat` |
| 运行表 / 样本表 / compare | `core/components/table/data-table.tsx` | 直接用，配列定义 |
| JSON 只读展示 | `core/components/ui/json-cell.tsx` | 保留只读，编辑场景换 Monaco |
| 评测流量进 Trace | `BaseLLM` 切面 + `observe/*` + `channel` 体系 | 透传 `channel='eval'`，不新增切面 |
| eval 渠道 | `channel='playground'`（playground/service + graphs/runner） | 加 `'eval'` 取值，参照写法 |
| 低分下钻 | `MetricDistribution.low_score_item_ids` | 已有，前端画出来 + 优化器消费 |
| 优化产出落点 | `DatasetRunDetail.prompt_override` | 已有字段，落优化后 Prompt |
| 多 run 对比 | `run-compare-matrix.tsx` | 已有 item-by-item，补 win/tie/loss + diff |
| RAGAS 评分 | `template_scoring.py`（红线禁改 weight） | 保留为 judge 的一种模式，不动 |
| PII 策略 | `pii.py`（mask/drop/keep） | 编辑/导入/扩样复用 |
| 模型列表数据源 | `GET /v1/admin/models`（已存在） | model-picker 直接调，无需建端点 |

---

## 五、优先级矩阵 + 分期执行顺序

### 优先级矩阵

| 模块 | 优先级 | 工作量 | 类型 |
|------|--------|--------|------|
| A 汉化 + 选择器化 | **P0** | S | 可用性底线 |
| B 专业 JSON + 全字段编辑 | **P0** | M | 可用性底线 |
| D eval 渠道入 Trace | **P0** | S | 基建前置 |
| E 运行详情重做 | **P0** | M | 可用性底线 |
| C Excel 导入导出 | P1 | S–M | 产品化 |
| F 运行 tab 分析统计 | P1 | M | 产品化 |
| G judge 多模式 + GSB + AI 评分 + DSL | P1 | L | 核心增量 |
| H1 playground 调试升级 | P1 | M | 闭环起点 |
| H2 AI 扩样 + 表格编辑 | P2 | M | 差异化 |
| H3 智能优化 + diff + 版本 | P2 | L | 差异化终点 |

### 推荐分期

**第 1 期（可用性夯实，2 周内）— 全 P0**
A（汉化 + model-picker）→ D（eval 渠道，先铺，后续都挂它）→ B（Monaco + 全字段编辑）→ E（运行详情重做）。
完成即「非工程师能从采样到看分析全流程走通」。

**第 2 期（产品化闭环，3–4 周）— P1**
C（Excel 导入导出）→ F（运行 tab 分析）→ G（judge 多模式，先 `llm_score` 1-5 + reason 救活 llm_judge，再 GSB，DSL 可视化配置后置）→ H1（playground `{{var}}` + 存为种子 + 基于回答改写）。
完成即「Prompt 工程师能调好→存样本→配多模式评分→跑批→看理由下钻」。

**第 3 期（差异化智能，按需 4–6 周）— P2**
H2（AI 扩样 + 电子表格编辑）→ G 的 DSL 文本高级出口 → H3（智能优化 + 报告 + 前后 diff + 版本追溯）。
完成即「评测平台 → Prompt 优化平台」。

**排序逻辑**：D 必须在 G/H 之前（评测/优化流量要进 Trace）；B 在 H 之前（表格编辑依赖 Monaco/全字段）；G 的 judge 契约升级一次到位，GSB/DSL/AI 评分都挂上去；H3 依赖 G（要分数和低分共性才能优化）+ E（要 diff 视图基座）。

---

## 六、已定决策（2026-06-04 用户拍板）

**范围**：**全量到 PromptPilot 级**（A–H 八模块全做，3 期推进）。**AI 能力全做**（AI 智能评分 + AI 扩样 + 一键优化 Prompt）。**judge 完整升级**（`JudgeResult` 契约 + 1-5 量纲 + GSB + AI 评分 + 评分 DSL）。

| 决策点 | 定论 |
|--------|------|
| D1 JSON 编辑器 | **CodeMirror 6**（~200KB，高亮+校验+格式化够用；前端无 Monaco 依赖，不拖首屏） |
| D2 Excel 解析 | **前端 SheetJS 解析 + 本地预览 → 复用现有 `/bulk-import` 端点**；PII 仍后端兜底 |
| D3 评分量纲 | **内部存 [0,1] 不变，UI 层映射 1-5 显示**（不污染 RAGAS / mean_score / 统计） |
| D4 评分 DSL | **做**，分两步：第 2 期先可视化配置面板（覆盖多数 JSON 逐字段评分场景），第 3 期补 DSL 文本解析器作为高级出口 |
| D5 GSB 参照答案 | **新增 `reference_output` 字段**（与 `expected_output` 金标准语义区分，加列不改列） |
| D6 AI 能力模型/上限 | judge/扩样/优化默认走**系统默认 chat 模型**（eval 配置里可改）；**评测集大小 + 优化轮次设硬上限**防 token 失控；AI 扩样**纯 LLM 生成，不联网** |
| D7 智能优化深度 | **只做 Prompt 改写 + 优化报告 + 前后 diff + 版本追溯**，不做模型微调/精调 |

> 全量是分 3 期、约 6 周+ 的工程；按「第 1 期全 P0 → 第 2 期 P1 → 第 3 期 P2」分轮执行，每期完成即可独立交付价值，不必一次做完。

---

## 七、不做 / 暂缓清单（划清边界）

- **不做模型微调 / 免费精调**（PromptPilot 有，基建成本不匹配，Q7）。
- **不做联网生成变量**（无联网基建，AI 扩样先纯 LLM，Q6）。
- **不动 RAGAS 红线**（`template_scoring.py` weight/定义禁改，只作为 judge 的一种模式并存）。
- **不推倒数据模型**（`input_payload/expected_output/prompt_override/low_score_item_ids` 复用，只加列）。
- **不新增 Trace 切面**（eval 渠道复用 `BaseLLM` + `observe` 现有切面）。
- **DSL 文本编辑后置**（先可视化配置覆盖多数场景，Q4）。

# 评测域「顶级化」重塑 — 设计 SSOT

> 触发：用户真实使用反馈（运行抽屉套娃 / 样本删不掉无批量无分页 / 电子表格英文表头读不动 / 评分模板·评测任务不会用 / 评测调用看不到 trace）。
> 用户拍板方向：**一次做到顶级** + **运行全页路由** + **评估工作流一体化（方案C）**。
> 本文是 SSOT，每阶段照它推进 → tsc/eslint/ruff/import-linter 全绿 → 浏览器/真实 e2e → commit。

---

## 0. 诊断纠偏（实证）

**Trace 不是后端断链**：`call_logs` 实测有 **165 条 `channel='eval'`**（DSL/llm_score/gsb/优化/改写都在，最近即本次 e2e）。GenerationRecorder 挂在工厂层、TraceContext 盖了 eval 章，录制完全正常。用户看不到 = **前端 Trace 页没暴露 eval 渠道**（过滤掉了 / 渠道筛选无 eval 选项）。→ 这是前端放量 + 下钻问题，不是重做可观测。

四个真问题（对到顶级产品 Langfuse / Braintrust / Dify Eval）：
1. **运行交互**：详情/样本/优化/对比全塞抽屉，垂直叠 2-3 层，返回即丢上下文。顶级做法 = run 详情独立整页 URL + master-detail，对比侧栏滑出不弹 modal。
2. **数据管控**：表格视图无删除键（只电子表格有）、无批量删、无分页（一次拉 200）、采样无确认/回滚。→ 管不动就不敢放真数据。
3. **电子表格**：表头甩 `hash`/`token_count` 原文、长值硬截断点不开、系统列挤版面。
4. **模板/任务**：后端 EvalJob 已支持绑模板，前端表单根本没"选模板"入口；模板/judge/任务三概念平行摆着没串。

**贯穿主线缺失**：没有 **数据集 → 跑一次 → 逐样本看(连 trace) → 对比/优化 → 再跑** 这条顺下来的主线，也没让用户信任地往里放真数据。立住这两条 = 从"功能齐全"跨到"顶级"。

---

## 1. 架构决策（定死）

### D1. 评估工作流一体化（方案C）走「概念/UX 层统一，不动底座」
- **不合并** DatasetRun / EvalJob 数据模型（它俩已共用 `datasets.runner.run_dataset`，强行合并 = 高风险、动路由/权限/迁移）。
- 引入统一概念 **「评分方案 (Scoring Scheme)」** = "如何打分"的唯一答案，二选一：
  - **保存的 EvalTemplate**（多 metric 加权，已有，版本化）
  - **内联 judge 配置**（judge + judge_config，6 种 judge）
  这一步消解"评分模板 vs 逐任务配 judge"的割裂。
- 统一入口 **「新建评估 (Evaluation)」**：选数据集 → 选评分方案 → 选「立即跑」或「定时」 → 看结果。
  - 立即跑 → 建 DatasetRun（现有 run 端点）
  - 定时 → 建 EvalJob（现有 job 端点）
  - 两条都引用同一个评分方案（template_id **或** judge+judge_config）
- 菜单从属层级：**数据集 → 评分方案库（EvalTemplate）→ 评估运行/定时任务**。eval-jobs 收敛为"定时评估"，eval-templates 升级为"评分方案库 + onboarding"。

### D2. 运行 = URL 驱动的整页 master-detail
- 新路由 `/datasets/:id/runs/:runId`（run 详情整页：左 run 列表 / 右详情含分数分布 + 样本表 + 样本详情侧栏）。
- 新路由 `/datasets/:id/runs/compare?ids=a,b,c`（对比整页）。
- 抽屉降级为"快速预览"（列表点 run 可选 drawer 速览 or 跳整页）；优化从 modal 改抽屉/整页区；样本对比侧栏滑出不再弹 modal。
- 状态走 URL（可分享、前进后退），不再 useState + modal 套娃。

### D3. Trace 放量 + 下钻，不重做可观测
- 前端 Trace/观测页：渠道筛选加 `eval`、默认不排除 eval；eval 根行补 model/cost（若缺）便于渲染。
- run 详情 / 样本详情：从"这条样本"下钻到它那次真实 LLM 调用的 trace（按 request_id / call_log 关联）。

### D4. 数据可管控是底线
- 表格 + 电子表格统一删除入口；多选 + 批量删端点；分页（同 Trace 列表 page/page_size + keepPreviousData）；采样有预览确认 + "撤销这批"。

---

## 2. 分阶段执行计划

### Phase A — 救命：数据管控 + Trace 放量（P0，先做）
- **A1 Trace 放出 eval**：前端观测/Trace 页渠道筛选含 eval、不默认排除；eval 根行 model/cost rollup（缺则补，参考 dashboard/observability 既有 rollup）；run item → trace 下钻入口。
- **A2 样本删除/批量/分页**：
  - 后端：`list_items` 加 page/page_size → `PageResult[DatasetItemItem]`（默认兼容旧 limit）；新增 `POST /datasets/{id}/items/batch-delete {item_ids}`（单次重算 item_count）。
  - 前端：表格视图加删除键（与电子表格统一）；两视图加行多选 checkbox + 工具条「删除已选 N 条」；TablePagination 接入（复用 datasets-page keepPreviousData）。
- **A3 采样确认/回滚**：sample-from-logs 完成后展示结果摘要 + "查看新增 N 条" + "撤销这批采样"（按本次采样标记/时间窗批量删）。

### Phase C — 运行整页 master-detail（P1，运行主线）
- 新路由 + RunDetailPage（左 run 列表 / 右详情：分数分布 + 样本表 + 样本详情侧栏，样本侧栏含"该样本在其他 run 的表现"迷你对比 + trace 下钻）。
- RunComparePage（整页对比，URL 驱动多版本）。
- dataset-detail-page runs tab：点 run → 跳整页（抽屉留快速预览）；优化改抽屉/整页区；拍平嵌套。

### Phase B — 评估工作流一体化（方案C，P1，模板/任务打通）
- "评分方案"概念：eval-job-form + run-start-modal 统一一个「评分方案」选择器（选模板 or 自定义 judge），共用组件。
- 后端：`/eval-templates/{id}/usage-count`；eval-templates 标 `is_builtin`；EvalJob 出参补 template_name/version；run 端点 template_id 已支持（确认透传）。
- 「新建评估」统一入口：选数据集 → 评分方案 → 立即/定时 → 结果。eval-templates 页加 onboarding + 应用数 + 内置方案库；导航分层。

### Phase D — 电子表格 Airtable 化（P2，打磨）
- 列名中文映射表（user_input→用户输入 / hash→哈希 / token_count→Token 数…）+ 系统列可隐 + 列菜单。
- 单元格 hover/点击预览（Popover/Tooltip + JSON 语法高亮）；列宽按类型自适应；长值省略可预览。

---

## 3. 执行纪律
- 每阶段：Workflow 多 agent 实现 + adversarial 复核 → 主进程 tsc/eslint/ruff/import-linter 全绿 → 浏览器/真实 e2e → commit。
- **分支**：当前在 `refactor/newapi-gateway`（评测工作已在此，迁移耦合 p27_a01）。本重塑继续在此分支，合并策略见 memory `eval-domain-loop`。
- 不碰 newapi 文件（model_def/factory(provider 侧)/providers/p27_a01）。
- 顺序：A（救命）→ C（运行主线）→ B（评估一体化）→ D（打磨）。A 完先验收，再往下。

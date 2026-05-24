# Chameleon 全站 UI 高级化改造方案

> 目标：把产品从"后台管理系统"质感拉到"高级 AI 产品"质感。少用传统表格，多用卡片 /
> 抽屉 / 语义化状态 / 数据可视化。参考 dify、langfuse、one-api(Berry)、FastGPT、ragflow、
> lobe-chat 的交互范式，结合自有 Tailwind + shadcn 风格 UI 库逐页落地。
>
> 日期：2026-05-24 · 状态：方案待评审

---

## 0. 现状诊断

### 0.1 已经高级化（卡片 / 图表 / 抽屉，不动或仅微调）

dashboard、cost-dashboard、conversations(+detail)、datasets(+detail)、eval-jobs、graphs、
graph-editor(React Flow)、marketplace、template-gallery、plugins、workspaces、playground、
login。**三大配置面（models / providers / channels）本轮已抽屉化**，workspaces 列表本轮已卡片化。

### 0.2 仍是传统表格 / 低级表单（改造目标，按"丑"排序）

| 优先 | 页面 | 现状 | 目标范式 | 参考 |
|------|------|------|---------|------|
| P1 | call-logs | 裸 DataTable + 分页 | 智能日志表：状态 pill / token·cost·latency 格式化列 / 模型 pill / filter bar + 时间范围 / 行展开看 IO / trace 链接 | langfuse traces 表、one-api Log |
| P1 | audit-logs | 裸 DataTable + 分页 | 同上（无 cost，强调 actor / action / 资源 / 时间轴） | langfuse、one-api |
| P2 | providers(list) | DataTable | 卡片网格：logo + 已配/未配 + 模型数 + hover 配置（抽屉已有） | dify provider 卡、dify app card |
| P2 | channels(list) | DataTable | smart-cell 表：响应时间色阶健康标签 + 测试按钮即时反馈 + 批量启停 + 优先级内联编辑 | one-api Channel |
| P2 | models(list) | DataTable（参数 chips 本轮已加） | 保留表但加 provider logo + 测试即时反馈，或卡片化 | dify model、one-api |
| P3 | abilities | 矩阵 DataTable | 按 group 分组卡 / 可视化路由矩阵 | dify、one-api group |
| P3 | settings | 8 个 manual tab + 裸 input 堆叠 | 统一 Tabs + 字段分组卡 | dify account-setting |
| P3 | users | DataTable | 加头像 + 角色 pill + 状态 + 内联操作（或卡片） | one-api User |
| P3 | roles | DataTable（权限抽屉已有） | 列表加权限计数 / 分类标签 | — |
| P4 | embed-configs | DataTable | 卡片 + 代码预览 | dify |
| P4 | workspace-members | DataTable | 加头像 + 角色 pill（成员页已有基础） | — |

### 0.3 设计系统盘点（先复用，缺的才建）

**已有**：Button / Card / Badge / Input / Textarea / Select / Switch / Tooltip / Modal /
Sheet(抽屉) / Dialog / DropdownMenu / Table / ParamSlider / SectionCard / DataTable /
TableToolbar / TablePagination / ConfirmDialog / EmptyState / Skeleton / DateRangePicker /
PageHeader / Spinner / JsonViewer / VirtualList / CommandPalette / PermissionGuard /
JSONSchemaForm（+ widgets）。

**缺的原子件（基建先行）**：

| 组件 | 用途 | 参考 |
|------|------|------|
| `StatTile` | 大数字指标卡：label / value / delta / 可选 sparkline | langfuse BigNumber、one-api StatisticalLineChartCard |
| `StatusBadge` | 语义色状态 pill + 可选 live ping dot | langfuse status-badge / level-colors |
| `Tabs` | 替代各 detail 页手写 tab（agent / kb / settings / eval） | dify |
| `SegmentedControl` | 视图切换 / 枚举单选（如 tree↔timeline、log type） | — |
| `Chart`(wrapper) | 封装 recharts：LineTimeSeries / Bar / Area + 统一 formatter + 空态 + 骨架 | langfuse chart-library |
| `LogTable`(pattern) | DataTable + filter bar + 时间范围 + 行展开 IO + token/cost/latency 列 + 行高切换 | langfuse traces 表 |
| `format` utils | `formatTokens` / `formatCost` / `formatLatency`（`formatRelative`/`formatDateTime` 已有，先 grep 复用） | — |

---

## 1. 设计原则（提炼自参考项目）

1. **列表优先卡片网格 + hover 显操作**——静息态干净，操作三点/按钮 hover 才出（dify app/dataset card）。
2. **配置走右侧抽屉**，不用居中弹窗——本轮 models/providers/channels 已落地，后续编辑面沿用。
3. **日志/可观测专项**：语义色状态 pill + live dot；token/cost/latency **紧凑格式化**（如 `1.2K` `$0.0034` `820ms`）；大 IO **延迟渲染**（不塞进主表）；filter builder + 统一时间范围；行高 s/m/l 切换（langfuse）。
4. **运营资源**：行内健康标签（响应时间色阶 绿<1s/蓝<3s/黄<5s/红）、测试按钮即时反馈、批量启停、优先级内联编辑（one-api Channel）。
5. **仪表盘**：大数字 StatTile（label/value/delta/sparkline）+ 时序图 + 维度 breakdown 表。
6. **统一 token**：颜色全走主题变量（禁硬编码 hex）、间距/圆角(`rounded-xl` 卡 / `rounded-lg` 控件)/阴影成体系；空态 dashed 容器 + 文档/CTA；加载用骨架屏。
7. **渐进式披露**：collapsible（如 provider 卡折叠模型列表）、hover card、tooltip 兜住密度。

---

## 2. 分阶段路线图（按 ROI 排序）

> 每阶段产出可独立合并；**每页改完用 Chrome MCP 截图核实**（无折行/溢出/错位）再提交。

### Phase 1 — 基建 + 最丑的日志页（最高 ROI）
- 建 `StatTile` / `StatusBadge` / `Tabs` / `Chart` wrapper / 格式化 utils（grep 复用优先）。
- **call-logs + audit-logs** → 智能日志表：状态 pill、token/cost/latency 格式化列、模型 pill、filter bar + 时间范围、行展开看 IO/trace 链接。
- 验收：截图。

### Phase 2 — 运营资源列表
- **providers** → 卡片网格（logo + 已配/未配 + 模型数 + hover 配置；抽屉保留）。
- **channels** → smart-cell：健康标签（响应时间色阶）+ 测试按钮 + 批量启停 + 优先级内联。
- **models** → provider logo + 测试即时反馈（参数 chips 已做）。
- **abilities 矩阵** → 分组卡 / 可视化。

### Phase 3 — 表单与权限页
- **settings** → 统一 `Tabs` + 字段分组卡（不再裸 input 堆叠）。
- **users** → 头像 + 角色 pill + 状态 + 内联操作。
- **roles** → 列表加权限计数/分类（权限编辑抽屉已有）。
- **embed-configs** → 卡片 + 代码预览。

### Phase 4 — 可观测深化
- **trace-detail** → tree + timeline 双视图（langfuse），`react-resizable-panels` 可调面板。
- **eval-jobs/detail** → score badges、状态 live dot、趋势图复用 `Chart`。
- **dashboard / cost** → 抽出复用 `StatTile` + `Chart`，与新基建对齐。

---

## 3. 不做 / 风险边界

- **不引入 MUI**：one-api(Berry) 是 MUI，只借鉴交互不照搬技术栈；继续 Tailwind + 自有 ui 库。
- **不全站重写**：按页渐进，每页改完浏览器验证（per-change，见 [[feedback-verify-ui-in-browser]]）。
- 大列表用已有 `VirtualList`；HTTP 仍只在 `services/`，不进组件。
- 颜色禁硬编码 hex，走主题变量；不破坏现有 service 契约；TS strict 必过。

---

## 4. 验收标准

- 每页改完 Chrome MCP 截图核实（无折行/溢出/错位）。
- 复用既有组件优先；新原子件单一职责、可跨页复用。
- TS strict + 既有 e2e 不回归。

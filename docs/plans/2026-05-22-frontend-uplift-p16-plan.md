# P16 前端做厚 实现计划

**Date**: 2026-05-22
**Owner**: links
**Design ref**: [2026-05-22-frontend-uplift-p16-design.md](./2026-05-22-frontend-uplift-p16-design.md)

## 0. 节奏总览

按"基础件先升 → 数据层重构 → 顶层体验"的顺序，避免后续返工：

| 阶段 | 子项 | 估时 | 累计 |
|---|---|---|---|
| ① | P16-D Sheet → Modal | 0.5d | 0.5d |
| ② | P16-E.4 微交互升级 | 1.5d | 2.0d |
| ③ | P16-B Provider/Model 测试调整 | 0.5d | 2.5d |
| ④ | P16-A Config-as-DB | 1.5d | 4.0d |
| ⑤ | P16-E.1 真数据 Dashboard | 1.5d | 5.5d |
| ⑥ | P16-E.3 ⌘K 命令面板 | 1.0d | 6.5d |
| ⑦ | P16-C KB Dify 量级 | 5.0d | 11.5d |
| ⑧ | P16-E.2 Trace Drawer + Playground | 3.0d | 14.5d |

**总估时**：~14.5 天（单人全栈估算，含联调）。

**单 commit 原则**：每个 task 独立 commit；每阶段完结后跑一次冒烟。

---

## ① 阶段：P16-D Sheet → Modal（0.5d）

### Task D1 — 新建 Modal 组件 + 配套 hook

**文件**：
- `frontend/src/core/components/ui/modal.tsx`（NEW）
- `frontend/src/core/hooks/use-modal-dirty.ts`（NEW）
- `frontend/src/core/components/ui/index.ts`（修改：export Modal）

**要点**：
- 基于 `@radix-ui/react-dialog`
- props: `open / onOpenChange / size: "sm"|"md"|"lg"|"xl" / closeOnBackdrop / preventCloseWhenDirty / initialFocus`
- 子组件：`Modal / ModalHeader / ModalBody / ModalFooter`
- 动画：fade 150ms + scale 0.96→1（Radix Dialog 自带 `data-state` 钩 Tailwind animate-in/out）
- 遮罩：`bg-stone-950/40 backdrop-blur-sm`
- 容器：`rounded-2xl border-stone-200 shadow-pop bg-paper`
- `useModalDirty()`：返回 `setDirty / confirmClose / dirty`，confirmClose 时若 dirty 弹原生 confirm（或自实现二级 confirm Modal）

**验收**：
- Modal sm/md/lg/xl 视觉对齐 waveflow 风格
- ESC、点遮罩、关闭按钮 都能关
- preventCloseWhenDirty=true 时改了内容直接 ESC 弹"未保存"提示

### Task D2 — 8 业务页 Sheet → Modal 改造

**文件**（每页一个改动）：
- `frontend/src/system/providers/pages/providers-page.tsx`（CreateProviderSheet → CreateProviderModal, size=lg）
- `frontend/src/system/models/pages/models-page.tsx`（size=md）
- `frontend/src/system/agents/pages/agents-page.tsx`（size=md）
- `frontend/src/system/kbs/pages/kbs-page.tsx`（size=md）
- `frontend/src/system/users/pages/users-page.tsx`（size=md）
- `frontend/src/system/apps/pages/apps-page.tsx`（size=md）
- `frontend/src/system/embed_configs/pages/embed-configs-page.tsx`（size=lg）
- `frontend/src/system/roles/pages/roles-page.tsx`（size=md）

**保持不变**：
- Sheet 组件（sheet.tsx）保留不动
- 任何"详情查看 / 批量操作面板" 类需求**不在本 task**

**验收**：
- 8 页创建表单全部居中弹出（不再右侧滑出）
- Tab 顺序 / focus / submit / cancel 行为一致
- 没有 console error

### Task D3 — 冒烟 + commit

跑一遍 8 页创建流程，截屏 commit message 描述。

---

## ② 阶段：P16-E.4 微交互升级（1.5d）

### Task E4.1 — Toast wrapper

**文件**：
- `frontend/src/core/lib/toast.ts`（NEW，封装 sonner）

**实现**：
```ts
export const toast = {
  success, error, warning, info, loading, promise, dismiss
}
```
- 每种状态自带 icon（lucide check-circle / x-circle / alert-triangle / info / loader）
- `action` 参数支持 `{label, onClick}`
- `promise` 处理 loading→success/error 状态自动切

**全站替换** `import { toast } from 'sonner'` → `import { toast } from '@/core/lib/toast'`（grep 替换）。

**验收**：toast 多种状态 + action 按钮在登录 / 创建 / 删除场景能用。

### Task E4.2 — EmptyState 组件 + 接入

**文件**：
- `frontend/src/core/components/common/empty-state.tsx`（NEW）
- 11 个业务页 `emptyText` → `emptyExtra` 走新组件（datatable.tsx 已有 emptyExtra prop）

**实现**：
- props: `icon / title / description / action?`
- 默认布局：垂直居中，icon 48px outline + title 14px + description 12.5px stone-500 + action

**11 页面对应插画**（用 lucide-react outline icons 即可，二期换 SVG 插画）：
- users: `Users` / agents: `Bot` / models: `Cpu` / providers: `Cloud` / kbs: `Library` / apps: `Key` / embed_configs: `Code2` / roles: `Shield` / call_logs: `FileText` / audit_logs: `History` / settings: `Settings`

**验收**：每个空状态有图标 + 文案，按钮可点。

### Task E4.3 — Tooltip / Popover 全覆盖

**文件**：
- `frontend/src/core/components/ui/tooltip.tsx`（已有？检查；没有则新建）
- 所有 11 业务页 columns header：`header: t('table.xxx')` → `header: <ColumnHeader title={t('table.xxx')} hint={t('table.xxx_hint')} />`
- 所有 status badge：包 Tooltip 显含义
- 所有 icon-only 按钮：包 Tooltip 显 action 名（已有部分，补全）

**新建组件**：`ColumnHeader`（`<span>{title} <HelpCircle className="opacity-40 hover:opacity-100" /></span>` 包 Tooltip）

**i18n**：补充 `table.*_hint` key（描述字段含义），约 20 条。

**验收**：表头悬停显字段含义；icon 按钮悬停显 action 名。

### Task E4.4 — Inline edit（DataTable 内）

**文件**：
- `frontend/src/core/components/table/inline-edit-cell.tsx`（NEW）
- 选 3-5 个表格字段试点：
  - `models.temperature`（number）
  - `kbs.default_top_k`（number）
  - `agents.description`（text）
  - `documents.tags`（chips）

**实现**：
```tsx
<InlineEditCell
  value={x.temperature}
  type="number"
  min={0} max={2} step={0.1}
  onSave={async (v) => await modelApi.update(x.id, { temperature: v })}
/>
```
- 默认显示文本；hover 出现"铅笔"图标；双击或点铅笔 → input；blur/Enter 保存（optimistic update + toast）

**验收**：点 3-5 个字段能直接改且乐观更新。

### Task E4.5 — Optimistic update 全面化

**文件**：所有 mutation 的 `useMutation({ onMutate, onError, onSettled })`
- `agents.enabled` / `users.status` / `apps.enabled` / 各 inline edit

**模式**：
```ts
const mut = useMutation({
  mutationFn: ...,
  onMutate: async ({ id, enabled }) => {
    await qc.cancelQueries(['agents'])
    const prev = qc.getQueryData(['agents'])
    qc.setQueryData(['agents'], (old) => old.map(a => a.id === id ? { ...a, enabled } : a))
    return { prev }
  },
  onError: (_e, _v, ctx) => qc.setQueryData(['agents'], ctx.prev),
  onSettled: () => qc.invalidateQueries(['agents']),
})
```

**验收**：toggle / inline edit 不等接口返回即时变化，失败回滚。

### Task E4.6 — Skeleton 完善

**文件**：
- `frontend/src/core/components/common/skeleton.tsx`（已有 `.skeleton` class；新增组件包装：`<Skeleton width={...} height={...} />`、`<SkeletonText lines={3} />`、`<SkeletonCard />`）

**接入**：Dashboard / Trace Drawer / KB chunk 墙 / Playground 流式 loading

**验收**：以上场景 loading 期间有 shimmer。

---

## ③ 阶段：P16-B Provider/Model 测试调整（0.5d）

### Task B1 — 后端

**文件**：
- `backend/chameleon-api/src/chameleon/api/routes/providers.py`（删 test endpoint）
- `backend/chameleon-providers/src/chameleon/providers/services/provider.py`（删 test_connection）
- `backend/chameleon-api/src/chameleon/api/routes/models.py`（NEW endpoint `POST /v1/admin/models/{id}/test`）
- `backend/chameleon-providers/src/chameleon/providers/services/model.py`（NEW `test_model(id) -> TestResult`）

**TestResult schema**:
```python
@dataclass
class TestResult:
    ok: bool
    latency_ms: int
    sample: str
    detail: str
```

**实现**：LLM 用 `chat("ping")` max_tokens=5；embedding 用 `embed("hello")` 拿向量 dim。失败捕异常入 detail。

**验收**：`curl POST /v1/admin/models/{id}/test` 对 qwen-plus 返 `{ok: true, latency_ms: 234, sample: "pong", detail: "延迟 234ms · ..."}`

### Task B2 — 前端

**文件**：
- `frontend/src/system/providers/pages/providers-page.tsx`（删 testMut + Zap + 测试按钮）
- `frontend/src/system/providers/services/provider.ts`（删 test）
- `frontend/src/system/models/pages/models-page.tsx`（加 testMut + 行操作"测试"按钮 + 结果 toast）
- `frontend/src/system/models/services/model.ts`（加 test）
- `frontend/src/core/i18n/locales/{zh-CN,en-US}.json`（补 actions.test_model_hint）

**验收**：providers 页无测试按钮；models 页点测试 toast 显延迟 + 回包。

---

## ④ 阶段：P16-A Config-as-DB（1.5d）

### Task A1 — schema + Pydantic

**文件**：
- `backend/chameleon-core/src/chameleon/core/config/system_settings_schema.py`（NEW）
- `backend/chameleon-core/src/chameleon/core/models/system_setting.py`（NEW SQLAlchemy ORM）
- `backend/chameleon-core/src/chameleon/core/models/model_default.py`（NEW）

**schema 内容**：14 个 setting（见 design §1.1）。

**辅助函数**：
```python
def get_setting(session, key: str, default: Any = _NOT_SET) -> Any:
    """读 DB；若不存在用 schema default；schema 也没有用调用者 default。"""

def set_setting(session, key: str, value: Any, user_id: int):
    """upsert 一行。"""

def reset_setting(session, key: str):
    """删 DB 行，使其回落到 default。"""
```

**验收**：单测 get/set/reset。

### Task A2 — Alembic migration

**文件**：
- `backend/migrations/versions/{ts}_add_system_setting_model_default.py`

**内容**：
- `CREATE TABLE system_setting`（含 update_at trigger 或 SQLAlchemy onupdate）
- `CREATE TABLE model_default`
- `--rollback DROP TABLE...`

**验收**：`alembic upgrade head` + `alembic downgrade -1` 双向通。

### Task A3 — Seed runner 扩展

**文件**：
- `backend/chameleon-system/src/chameleon/system/seed/runner.py`（扩 Phase B）
- `backend/chameleon-system/src/chameleon/system/seed/settings_seed.py`（NEW _seed_chameleon_settings）
- `backend/chameleon-system/src/chameleon/system/seed/agents_seed.py`（修改：用 baseurl_dict resolve 占位符）
- `backend/chameleon-system/src/chameleon/system/seed/models_seed.py`（修改：seed model_default）

**关键点**：
- 占位符 resolve：`${baseurl:xxx}` → `baseurl_dict[xxx]`；`${env:NAME}` → `os.environ.get(NAME)`
- api_key 走 `encrypt_api_key()` 写入 DB
- 仅首次（Phase B 内）跑

**验收**：清 DB 重启 → DB 里 system_setting 14 行、providers 3 条（带加密 key）、models 若干、model_default 2-3 条、agents 0-N 条；DB 非空时再启动不再读文件。

### Task A4 — API endpoints

**文件**：
- `backend/chameleon-api/src/chameleon/api/routes/system_settings.py`（NEW）
- `backend/chameleon-api/src/chameleon/api/routes/model_defaults.py`（NEW）
- `backend/chameleon-api/src/chameleon/api/routes/config_export.py`（NEW）

**endpoints**：见 design §1.3。

**导出实现要点**：
- 在内存中构建 4 个文件内容 + README.txt
- `zipfile.ZipFile` 打包到 `BytesIO`
- `StreamingResponse` 返 zip
- `Content-Disposition: attachment; filename="chameleon-config-{iso_ts}.zip"`
- 反查时 api_key 用 `decrypt_api_key()` 还原

**权限**：所有 endpoint 走 admin RBAC（permission `system:settings:*` / `system:config:export`），defaults.py 添加这两个权限点。

**验收**：postman 调过；导出 zip 解压后 4 个文件结构合理；明文 key 在文件中可见。

### Task A5 — 前端 Settings 8-tab 页

**文件**：
- `frontend/src/system/settings/pages/settings-page.tsx`（大改：94 行 → ~600 行）
- `frontend/src/system/settings/services/settings.ts`（NEW system_settings + model_defaults + export）
- `frontend/src/system/settings/components/settings-tab.tsx`（NEW 通用 tab 组件）
- `frontend/src/system/settings/components/setting-field.tsx`（NEW 单字段渲染器）

**Tab 内容**：
| Tab | 字段（来自 schema 的对应 key） |
|---|---|
| 通用 | log_level |
| 会话 | session.history_limit / title_max_length / ai_title_generation |
| 知识库默认 | knowledge.embedding_dim / default_top_k / chunk_size / chunk_overlap / ingest_concurrency |
| 流式 | stream.chunk_flush_ms / max_event_size_kb |
| 超时 | timeout.default_ms / dify_ms / fastgpt_ms / langgraph_ms |
| 调用日志 | call_log.retention_days |
| 模型默认 | （来自 model_defaults API：llm / embedding / vision） |
| 导入导出 | 一键导出按钮 + ⚠️ banner；上传导入（disabled） |

**渲染逻辑**：
```tsx
<SettingsTab title="会话">
  {schema.filter(s => s.group === 'session').map(s => (
    <SettingField key={s.key} schema={s} value={values[s.key]} onChange={...} />
  ))}
  <SaveButton dirty={dirty} onSave={handleSave} />
</SettingsTab>
```

**SettingField 类型分发**：
- `int / float` → `<Input type="number" min max step>`
- `bool` → `<Switch>`
- `str` → `<Input>`
- `select` → `<Select>` with `select_options`

**验收**：每个 tab 能改能存能重置；description tooltip 工作；改 chunk_size 后调用 KB 索引使用新值。

### Task A6 — 前端导出 + 警示 Modal

**文件**：
- `frontend/src/system/settings/components/export-section.tsx`（NEW）
- `frontend/src/core/components/layout/sidebar.tsx`（BottomUser 加 "导出配置" 菜单项）

**导出按钮**：
1. 点击 → 弹 `<Modal size="md">`：标题 "⚠️ 导出配置"，body 含警示文案（"导出文件含明文 API Key 与密码……"），底部 `[x] 我已了解风险并继续`，按钮 disabled until 勾选
2. 勾选后点"下载"→ 调 `GET /v1/admin/config/export`，浏览器下载 zip

**验收**：双入口（Settings tab + 用户菜单）能下到 zip；不勾警示不能继续。

---

## ⑤ 阶段：P16-E.1 真数据 Dashboard（1.5d）

### Task E1.1 — 后端 stats API

**文件**：
- `backend/chameleon-api/src/chameleon/api/routes/stats.py`（NEW）
- `backend/chameleon-core/src/chameleon/core/services/stats_service.py`（NEW，CallLog 聚合查询）

**Endpoints**：见 design §5.1。

**实现要点**：
- `overview`：4 个 stat 各一个 query（COUNT / SUM / COUNT distinct）
- `timeseries`：`date_trunc(:interval, created_at)` + group by dim
- `top`：order by metric desc limit
- `heatmap`：`extract(dow), extract(hour)` 二维 group

**性能**：单次查询 < 200ms（数据量 < 100w 行级）；超过用 materialized view（二期）。

**权限**：`stats:read` (admin / viewer)

**验收**：postman 调 4 个 endpoint 返结构正确数据；空数据返 0/[] 不报错。

### Task E1.2 — 前端组件库

**文件**：
- `frontend/src/core/components/common/date-range-picker.tsx`（NEW）
- `frontend/src/core/components/dashboard/stat-card.tsx`（NEW）
- `frontend/src/core/components/dashboard/trend-chart.tsx`（NEW）
- `frontend/src/core/components/dashboard/stacked-chart.tsx`（NEW）
- `frontend/src/core/components/dashboard/top-table.tsx`（NEW）

**库**：`yarn add recharts` (~50KB gzip)

**DateRangePicker**：preset 7 选 + 自定义日历选择；最终输出 `{from: Date, to: Date}`，存到 URL query string（深链友好）

**StatCard**：4 区——title / 主数值 / delta vs 上周期 / 内嵌 sparkline AreaChart

**TrendChart**：metric + groupby + interval 三个 select；recharts LineChart；x=ts y=value；多 dim 多色

**StackedChart**：recharts AreaChart with `stackId`；颜色按 dim hash 分配（保持稳定）

**TopTable**：常规表格 + 末列 share 进度条

**验收**：组件单独 storybook 或 demo 页可视化。

### Task E1.3 — Dashboard 页接入

**文件**：
- `frontend/src/system/dashboard/pages/dashboard-page.tsx`（大改）
- `frontend/src/system/dashboard/services/stats.ts`（NEW）

**布局**：见 design §5.2 ASCII 草图。

**验收**：选不同时间范围 / 不同 groupby，图表刷新无延迟错位；空数据有 EmptyState。

---

## ⑥ 阶段：P16-E.3 ⌘K 命令面板（1d）

### Task E3.1 — 后端 search API

**文件**：
- `backend/chameleon-api/src/chameleon/api/routes/search.py`（NEW）
- `backend/chameleon-core/src/chameleon/core/services/search_service.py`（NEW）

**实现**：每个 type 一个 `ILIKE %q%` 查询；types 参数过滤；总 limit。

**输出**：
```json
{
  "results": [
    {"type": "agent", "id": 1, "title": "客服 FAQ", "snippet": "DIFY 客服...", "url": "/agents/1", "icon": "bot"},
    ...
  ]
}
```

**权限**：`search:read`

**验收**：q="qwen" 返 model + provider 命中。

### Task E3.2 — 前端 CommandPalette

**文件**：
- `frontend/src/core/components/command/command-palette.tsx`（NEW）
- `frontend/src/core/components/command/command-item.tsx`（NEW）
- `frontend/src/core/services/search.ts`（NEW）

**库**：`yarn add cmdk` (~8KB)

**结构**：
- Radix Dialog + cmdk
- 居中浮层，宽 600 / max-h 70vh
- 顶部 input + 关闭快捷键提示
- 列表分组：搜索结果（动态） / 跳转 / 动作 / 最近访问

**最近访问**：localStorage `chameleon.recent_pages` 数组（max 10），路由变化时 push。

**全局快捷键**：`useHotkeys('cmd+k, ctrl+k', open)`（已用 / 没用 hotkeys 库则 useEffect 监听）

### Task E3.3 — mount + 注册命令

**文件**：
- `frontend/src/core/components/layout/main-layout.tsx`（mount `<CommandPalette />`）
- `frontend/src/core/components/layout/sidebar.tsx`（底部"搜索"按钮触发）

**命令清单**：见 design §7.3。

**验收**：⌘K 启动；输入 ag 显示 agents 命中；上下箭头 + Enter 跳转；动作"导出配置"打开导出 Modal。

---

## ⑦ 阶段：P16-C KB Dify 量级（5d）

### C.1 Bundle 1 — 闭环（1.5d）

#### Task C1.1 — schema + migration

**文件**：
- `backend/chameleon-core/src/chameleon/core/models/document.py`（NEW）
- `backend/chameleon-core/src/chameleon/core/models/chunk.py`（NEW，复用现有 chunk 表如果已有）
- `backend/chameleon-core/src/chameleon/core/models/agent_kb_link.py`（NEW）
- `backend/chameleon-core/src/chameleon/core/models/retrieval_evaluation.py`（NEW，C4 用，但 schema 一起出）
- `backend/migrations/versions/{ts}_add_kb_dify_grade.py`

**内容**：见 design §3.1。

**验收**：upgrade + downgrade 通；现有 KB 数据不影响。

#### Task C1.2 — parser dispatcher

**文件**：
- `backend/chameleon-knowledge/src/chameleon/knowledge/parsers/__init__.py`（dispatcher）
- `backend/chameleon-knowledge/src/chameleon/knowledge/parsers/pdf.py`
- `backend/chameleon-knowledge/src/chameleon/knowledge/parsers/docx.py`
- `backend/chameleon-knowledge/src/chameleon/knowledge/parsers/csv.py`
- `backend/chameleon-knowledge/src/chameleon/knowledge/parsers/html.py`
- `backend/chameleon-knowledge/src/chameleon/knowledge/parsers/url.py`
- `backend/chameleon-knowledge/src/chameleon/knowledge/parsers/markdown.py`
- `backend/chameleon-knowledge/src/chameleon/knowledge/parsers/text.py`

**库新增**（uv add）：`pypdf2 python-docx selectolax readability-lxml`

**Parser 协议**：
```python
class Parser(Protocol):
    mime_types: list[str]
    async def parse(self, source: bytes | str, *, name: str) -> ParsedDocument

@dataclass
class ParsedDocument:
    text: str
    metadata: dict   # title, author, page_count 等
```

**Dispatcher**：按 mime_type 选 parser，未注册返"unsupported"

**验收**：用每种 mime 一份 sample 文件能成功 parse 出 text。

#### Task C1.3 — ingest worker 改造

**文件**：
- `backend/chameleon-knowledge/src/chameleon/knowledge/services/ingest.py`

**新流水线**：
```
1. document insert → status=pending
2. status=processing
3. parser.parse(content) → text
4. chunk_strategy.split(text) → chunks
5. embedding.embed(chunks) → vectors
6. chunk insert + status=done
异常 → status=failed + error_message
```

**并发**：从 system_setting `knowledge.ingest_concurrency` 读。

**验收**：上传 1 个 PDF + 1 个 Word + 1 个 MD，三者都 status=done，chunk_count 大于 0。

#### Task C1.4 — APIs

**文件**：
- `backend/chameleon-api/src/chameleon/api/routes/kbs/documents.py`（NEW）

**endpoints**：见 design §3.2。

**验收**：postman 全套调通。

#### Task C1.5 — 前端 KB 详情页 + 文档 tab

**文件**：
- `frontend/src/system/kbs/pages/kb-detail-page.tsx`（NEW）
- `frontend/src/system/kbs/components/document-upload-zone.tsx`（NEW）
- `frontend/src/system/kbs/components/document-table.tsx`（NEW）
- `frontend/src/system/kbs/services/document.ts`（NEW）
- `frontend/src/router/`（加 `/kbs/:id` 路由）
- `frontend/src/system/kbs/pages/kbs-page.tsx`（行点击跳详情）

**库新增**：`yarn add @dnd-kit/core @dnd-kit/sortable`（拖拽上传）

**KB 详情页 tabs**（占位骨架，Bundle 2/3/4 填充）：
- 文档（Bundle 1）
- 检索测试（Bundle 2，占位）
- 评估（Bundle 4，占位）
- 配置（Bundle 3，占位）
- 概览（首屏 stat：文档数 / chunk 数 / token 数）

**验收**：上传 PDF/Word/MD/CSV/URL；列表显示状态；删除工作；进度轮询正常。

### C.2 Bundle 2 — 可看（1d）

#### Task C2.1 — chunks + search API

**文件**：
- `backend/chameleon-api/src/chameleon/api/routes/kbs/chunks.py`（NEW）

**Endpoints**：见 design §3.3。

**search 实现**：现有 retrieval_service.search 包一层，加 filter（tags/doc_ids）。

**验收**：postman 调通。

#### Task C2.2 — 前端文档详情页 + chunk 卡片墙

**文件**：
- `frontend/src/system/kbs/pages/kb-document-detail-page.tsx`（NEW）
- `frontend/src/system/kbs/components/chunk-card.tsx`（NEW）
- `frontend/src/router/`（加 `/kbs/:id/documents/:doc_id`）

**库新增**：`yarn add @tanstack/react-virtual`（chunks 多时虚拟滚动）

**卡片**：见 design §3.3。

**验收**：100+ chunks 文档进入不卡顿；hover 高亮；编辑保存触发 re-embed。

#### Task C2.3 — 检索测试 tab playground

**文件**：
- `frontend/src/system/kbs/components/retrieval-test.tsx`（NEW）

**接入** kb-detail-page 的"检索测试" tab。

**验收**：输 query → 显 top-k；改 top_k 滑杆实时刷新；query term `<mark>` 高亮。

### C.3 Bundle 3 — 可调（1d）

#### Task C3.1 — kbs / documents schema 扩展

**文件**：
- 上面 migration 已加 `chunk_strategy/default_top_k/recall_mode` 列；本 task 验证 ORM 字段 + Pydantic schema 加上

#### Task C3.2 — re-index API + 多策略

**文件**：
- `backend/chameleon-knowledge/src/chameleon/knowledge/services/chunker.py`（NEW，4 种策略实现）
- `backend/chameleon-api/src/chameleon/api/routes/kbs/documents.py`（加 reindex / update endpoints）

**Chunker 策略**：
- `fixed`：按 chunk_size 字数切，每段 overlap 字符
- `paragraph`：split `\n\n+` 后按段，单段超长再 fixed
- `sentence`：用 `regex r'[。！？.!?]\s*'` 切句，单句超长再 fixed
- `regex`：用户 separator

**验收**：四种策略各跑一份测试 doc，chunks 数符合预期。

#### Task C3.3 — 前端配置 tab + tag/metadata 编辑

**文件**：
- `frontend/src/system/kbs/components/kb-config-form.tsx`（NEW）
- `frontend/src/system/kbs/components/tag-editor.tsx`（NEW，chip 输入）
- `frontend/src/system/kbs/components/metadata-editor.tsx`（NEW，key-value list）

**验收**：改 chunk_strategy → "应用并重分块所有文档" 一键工作；document 加 tag / metadata 持久化。

### C.4 Bundle 4 — 可评（1.5d）

#### Task C4.1 — Hybrid retrieval + RRF

**文件**：
- `backend/migrations/versions/{ts}_add_chunks_tsvector.py`（NEW，加 content_tsv 列 + GIN 索引）
- `backend/chameleon-knowledge/src/chameleon/knowledge/services/retrieval.py`（扩 hybrid + RRF）

**实现**：
```python
async def search(kb_id, query, top_k, mode):
    if mode == "vector":
        return await vector_search(...)
    elif mode == "keyword":
        return await keyword_search(...)  # ts_rank
    elif mode == "hybrid":
        v = await vector_search(top_k=top_k * 2)
        k = await keyword_search(top_k=top_k * 2)
        return rrf_merge(v, k, top_k)

def rrf_merge(vec_hits, kw_hits, top_k, k=60):
    scores = defaultdict(float)
    for rank, hit in enumerate(vec_hits):
        scores[hit.chunk_id] += 1 / (k + rank + 1)
    for rank, hit in enumerate(kw_hits):
        scores[hit.chunk_id] += 1 / (k + rank + 1)
    # 取 top_k
```

**验收**：同 query 三种 mode 各能拿到结果；hybrid 通常综合排名更稳。

#### Task C4.2 — Evaluation API

**文件**：
- `backend/chameleon-api/src/chameleon/api/routes/kbs/evaluations.py`（NEW）
- `backend/chameleon-knowledge/src/chameleon/knowledge/services/evaluator.py`（NEW）

**实现**：
- 创建评估：input queries + expected_chunk_ids → 异步任务
- 批量跑 retrieval → 计算 hit@1/3/5 / MRR / latency_p50/p95
- 结果存 `retrieval_evaluation.results` JSONB

**验收**：上传 10-50 query 的 jsonl，5 min 内出结果；hit@5 / MRR 数值合理。

#### Task C4.3 — 前端评估 tab

**文件**：
- `frontend/src/system/kbs/components/evaluation-runner.tsx`（NEW，新建评估）
- `frontend/src/system/kbs/components/evaluation-list.tsx`（NEW，历史列表）
- `frontend/src/system/kbs/components/evaluation-detail-sheet.tsx`（NEW，Sheet 详情）
- `frontend/src/system/kbs/components/evaluation-compare-chart.tsx`（NEW，折线对比）

**验收**：上传 → 跑批 → 列表显结果 → 点查看详情 → 对比多批次趋势图。

### C.5 — Agent ↔ KB 关联（0.5d）

#### Task C5.1 — Agent KB API

**文件**：
- `backend/chameleon-api/src/chameleon/api/routes/agents.py`（加 linked-kbs endpoints）
- `backend/chameleon-core/src/chameleon/core/services/agent_kb.py`（NEW，service）

**Endpoints**：
```
GET  /v1/admin/agents/{id}/linked-kbs
POST /v1/admin/agents/{id}/linked-kbs/update    body: { kb_ids: int[] }
```

**验收**：postman 设置/查询关联。

#### Task C5.2 — Agent 详情页 + 关联 KB tab

**文件**：
- `frontend/src/system/agents/pages/agent-detail-page.tsx`（NEW，新建路由 `/agents/:id`）
- `frontend/src/system/agents/components/linked-kbs-form.tsx`（NEW）
- `frontend/src/router/` 加路由
- `frontend/src/system/agents/pages/agents-page.tsx`（行点击改为跳详情，不再 Sheet）

**Agent 详情 tabs**：基础信息 / 关联 KB / 关联模型 / 调用统计（占位）

**验收**：进入 agent 详情 → 多选 KB → 保存 → 重新进入仍在。

#### Task C5.3 — base_agent.retrieve() + echo 示例

**文件**：
- `backend/chameleon-core/src/chameleon/core/agents/base_agent.py`（加 `retrieve()` 方法）
- `backend/chameleon-agents/echo/src/echo_agent/agent.py`（演示用 retrieve）

**实现**：见 design §3.6。

**验收**：echo agent 调用时若挂了 KB，能拿到检索 context；call_log 里看 chunk hits。

---

## ⑧ 阶段：P16-E.2 Trace Drawer + Playground（3d）

### Task E2.1 — 后端 call_logs spans + detail API

**文件**：
- `backend/migrations/versions/{ts}_add_call_logs_spans.py`（加 `spans JSONB` 列）
- `backend/chameleon-api/src/chameleon/api/routes/call_logs.py`（加 `/v1/admin/call-logs/{id}/detail`）
- `backend/chameleon-core/src/chameleon/core/services/call_log_recorder.py`（修改：写入 spans）

**Spans 写入点**（在调用链各阶段记录 start_ms/end_ms）：
- auth check
- app validate
- model resolve
- provider request (含 SSE 流式时间)
- response build

**验收**：跑一次 agent 调用 → call_log 表里 spans 列含 5 段时间。

### Task E2.2 — 前端 JSON viewer 组件

**文件**：
- `frontend/src/core/components/common/json-viewer.tsx`（NEW，自实现）

**功能**：
- 缩进 / 折叠 / 高亮 / 复制 key/value / 搜索

**验收**：渲染 100KB JSON 不卡；折叠展开正常。

### Task E2.3 — 前端 TraceDrawer + 5 tab

**文件**：
- `frontend/src/system/call_logs/components/trace-drawer.tsx`（NEW）
- `frontend/src/system/call_logs/components/timeline-chart.tsx`（NEW）
- `frontend/src/system/call_logs/pages/call-logs-page.tsx`（行点击改为打开 Drawer）

**Drawer**：用 Sheet（size=lg），5 tab：Request / Response / Timeline / Logs / Raw。

**Timeline**：水平 div 拼接，每 span 一段 width = `(duration/total)*100%`，颜色按 span 类型；hover tooltip。

**Logs tab**：调 `GET /v1/admin/logs?request_id=` 拉关联日志（如果未来有，否则占位"日志归集二期"）

**验收**：call_log 行点击 → Drawer 打开 → 5 tab 切换正常；Timeline 可视化清晰。

### Task E2.4 — 后端 Playground API

**文件**：
- `backend/chameleon-api/src/chameleon/api/routes/playground.py`（NEW）

**Endpoint**：
```
POST /v1/admin/playground/invoke
body: {
  model_id?, agent_id?, system_prompt?, temperature, top_p, max_tokens,
  messages: [{role, content}],
  kb_ids?: int[]
}
Stream SSE: data: {"delta": "..."}\n\n
            data: {"end": true, "usage": {...}}\n\n
```

**实现**：复用 invoke_agent 或 model 直调；KB filter → 在 system_prompt 前 prepend 检索 context。

**权限**：`playground:invoke` (admin)

**验收**：postman / curl 调 SSE 流出 token。

### Task E2.5 — 前端 Playground 单列

**文件**：
- `frontend/src/system/playground/pages/playground-page.tsx`（NEW）
- `frontend/src/system/playground/components/param-panel.tsx`（NEW，参数滑杆）
- `frontend/src/system/playground/components/chat-column.tsx`（NEW，对话列）
- `frontend/src/system/playground/services/playground.ts`（NEW，SSE 调用）
- `frontend/src/router/` 加 `/playground` 路由
- `frontend/src/core/components/layout/sidebar.tsx` 加 Playground 菜单（"AI能力"组）

**SSE 实现**：
```ts
const response = await fetch('/v1/admin/playground/invoke', {
  method: 'POST', body, signal: abortController.signal,
})
const reader = response.body!.getReader()
const decoder = new TextDecoder()
while (true) {
  const { done, value } = await reader.read()
  if (done) break
  const chunk = decoder.decode(value)
  // parse SSE lines, dispatch delta to UI
}
```

**验收**：单列对话能流式出字；中途按"停止"立刻停。

### Task E2.6 — 前端 Playground 并排模式

**文件**：
- `frontend/src/system/playground/pages/playground-page.tsx`（继续扩）

**实现**：
- 顶部 "+ 加列" 按钮（max 4 列）
- 每列独立 model select + 参数（继承默认值）
- 发送：同时向所有列广播，独立 AbortController per 列
- 一列错另一列不影响

**导出**：列对话 JSON / Markdown 下载

**验收**：4 列 qwen-plus / deepseek-chat / gpt-4o-mini / 本地 echo 同时跑，结果并列；某列报错独立显示不阻塞其他。

---

## ⑨ 风险监控 / 收尾

### 9.1 阶段收尾 checklist

每个阶段结束跑：
- [ ] 前后端各跑一次 lint + tsc + pytest
- [ ] 用浏览器跑核心路径（不能只靠类型）
- [ ] 写一段 commit message 说明该阶段范围 + 影响
- [ ] 更新 README 如有用户感知变化
- [ ] 检查现有页面 / 流程没回归

### 9.2 全 P16 完成 checklist

- [ ] 14 个 setting 在前端可改可重置
- [ ] 4 个 config 文件能一键导出还原
- [ ] KB 上传 PDF/Word/MD/CSV/URL 全部成功
- [ ] 同一 KB 切 vector / hybrid / keyword 召回都能返结果
- [ ] 评估批次能跑通，hit@5 数据合理
- [ ] Agent 多选 KB 后调用能拿到上下文（echo agent 验证）
- [ ] 8 个 Sheet 全部变 Modal；Sheet 仅 Trace Drawer 用
- [ ] ⌘K 全站可用
- [ ] Dashboard 真数据 + 4 个图表
- [ ] Playground 1-4 列并排 SSE 流式
- [ ] 微交互全面：Toast / Empty / Tooltip / Inline edit / Optimistic / Skeleton

### 9.3 ADR 文档

完成后补写：
- `docs/adr/0013-config-as-db.md`
- `docs/adr/0014-kb-dify-grade-architecture.md`
- `docs/adr/0015-modal-vs-sheet-convention.md`（可选）

### 9.4 后续路线图（P17+ 不在本次）

- P17：节点画布（Dify 风 agent flow 编排）
- P18：Prompt 版本管理 + diff
- P19：Virtual Key 升级（quota / rate_limit / allowed_models）
- P20：插件市场 / Agent 市场
- P21：暗色主题完整支持
- P22：移动端响应式

---

## 10. 协作约定

- 每个 Task 独立 commit（commit msg 遵循 angular 规范，见 `~/.claude/rules/git.md`）
- 涉及 schema 改动的 Task 必须含 Alembic migration（含 rollback）
- 前端组件必须有 TS 类型 + i18n + 暗色测试（如适用）
- 后端 endpoint 必须有 OpenAPI + 权限检查
- 不写 docstring / 注释除非 why 非显然
- 遵循 `~/.claude/rules/python-codebase.md` / `react-codebase.md`

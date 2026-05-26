# 知识库升级：Dify 级文档交互与质量（参照 Dify / FastGPT）

> 状态：设计稿，待 review
> 定位：知识库是本项目重头戏，目标**文档交互 + 文档质量全面对齐 Dify**，FastGPT 作补充参照。
> 参照仓库（只作设计参照，不照搬代码）：`/Users/links/Coding/Hub/dify`

## 1. 现状盘点（比预想的全）

已具备、可直接复用：

| 能力 | 现状 | 位置 |
|---|---|---|
| KB 列表 / 详情 | 传统表格 + tab（概览/文档/集合/检索测试/评测/一致性/配置） | `kbs-page` / `kb-detail-page` |
| **创建** | ✅ 刚补：`POST /v1/admin/kbs` + `kbApi.create`（前端入口待建） | commit 1736665 |
| 文档上传 | 文件 / URL / 文本 → 异步 ingest（parse→split→embed→index） | `document-upload-zone` + `document_service` |
| 分段预览 | fixed / paragraph / sentence / regex / token 五模式，实时不写库 | `kb-chunking-preview-page` + `chunking-preview` API |
| 检索测试 | vector / keyword / hybrid + 多查询 + 标签过滤 + 分数拆解（vector/bm25/rerank） | `hit-test-panel` |
| 文档详情 | 文档信息 + chunk 网格（>60 虚拟墙）+ 标签 + 元数据 + reindex | `kb-document-detail-page` |
| chunk 卡片 | 查看 / 复制 / 展开（**编辑 onSave 未接 → 缺编辑/新增 API**） | `chunk-card` |
| 评测 / 一致性 / 集合 | 评测跑分、一致性扫描修复、collection CRUD | 各 service + tab |

**结论**：检索侧（vector/hybrid/keyword/rerank）已不弱于 Dify；**短板在「创建体验、段落级交互、分段质量、元数据体系、整体 UI」**。

## 2. Dify 功能对照矩阵（× = 缺，△ = 部分，✓ = 有）

| 维度 | Dify 能力 | 我们 | 差距 / 动作 | 优先级 |
|---|---|---|---|---|
| 列表 | 卡片网格 + 创建入口卡 + 标签筛选 | △ 表格、**无创建按钮** | 卡片化 + 创建入口 | P1 |
| 创建 | 多步向导（数据源→分段清洗→索引检索→处理完成），创建与首次导入合一 | × 无前端 | 建多步向导 | P1 |
| 数据源 | 文件 / Notion / 网站爬取 / 外部 API | △ 文件/URL/文本 | Notion/爬取/外部留后期 | P6 |
| 分段模式 | general / QA / **parent-child 分层** | △ 5 种「平铺」模式 | **加 parent-child + QA** | P4 |
| 文本清洗 | 去多余空白 / 去 URL·邮箱 / 停用词 | × | **加清洗规则** | P4 |
| 索引方式 | high_quality(向量) / economical(BM25) | △ 全部向量；recall_mode 三选 | 映射为「检索设置」，v1 不做纯 BM25 索引 | P1 |
| embedding 模型 | 可选 + 成本预估 | △ v1 全局单维（基本固定） | 向导里展示（多为只读/单选） | P1 |
| 检索设置 | 向量/全文/混合 + rerank + top_k + 阈值 + 权重 | ✓ 基本齐 | 接进设置/向导 | P1 |
| 文档列表 | 列（名/分块模式/字数/命中/状态）+ 启停开关 + 批量(启停/删/重建/导出/改元数据) + 排序 + 状态筛选 | △ 有表无启停/批量/排序 | **增强文档列表** | P2 |
| 段落管理 | 列表 + 查看/编辑/新增/删/启停 + 段内搜索 + 命中数 + 关键词 | △ 只查看 | **段落 CRUD + 启停（文档交互核心）** | P3 |
| 父子块 | parent 上下文 + child 块增删改 | × | 随 P4 分层分块 | P4 |
| 元数据 | dataset 级字段定义（类型）+ 每文档值 + 召回过滤 + 批量编辑 | △ 仅文档自由 meta | **元数据字段体系** | P5 |
| 设置页 | 基本信息/图标/权限 + 索引 + 检索 + 元数据字段 | △ 仅 chunk/topk/recall | 重排 + 补字段管理 | P2/P5 |
| 检索测试 | 文本/图片查询 + 历史 + 改设置 + 命中数回写 | ✓ 文本齐（图片留后） | 接命中数回写 | P2 |
| 标签 / 权限 / 图标 | 有 | × | 标签可早做；权限/图标后期 | P6 |
| 成本预估 / summary index / pipeline | 有 | × | 后期 / 不做 pipeline | P6 |

## 3. 取舍（v1 边界，避免无谓对齐）

- **embedding 单维**：现 `chunks.embedding VECTOR(1536)` 锁全局单维 → 创建时 embedding 模型基本只读/单选，不做"每库不同维"。索引方式不做纯 economical(无向量)，统一高质量向量 + 可选 keyword/hybrid 检索。
- **暂不做**：Notion / 网站爬取 / 外部 KB 作数据源、RAG pipeline 模式、权限分级、dataset 图标、图片查询、成本预估 token 预览。（列入 P6，按需再排。）
- **复用优先**：分段预览、检索测试、评测、一致性、集合全部保留复用，只重排 UI。

## 4. 数据模型变更（按阶段）

- **P3 段落管理**：`Chunk` 增 `enabled: bool`（启停，检索时过滤）、`keywords: JSON|None`、`hit_count: int`（检索命中累加）；新增 chunk 编辑/新增/删除/启停 API（reindex 单段 embedding）。
- **P4 分层分块**：`Chunk` 增 `parent_id: BigInt|None` / `kind`（parent/child/flat）+ `answer`（QA 模式）；`Document` 增 `chunking_mode`；chunker 加 parent-child / QA / 清洗规则。
- **P5 元数据**：新表 `kb_metadata_field(kb_id, key, label, type, options, builtin)` + `Document.meta` 存值；检索按 meta 过滤。
- **P2 文档启停**：`Document` 增 `enabled: bool`。
- 迁移按惯例 formatted SQL changeset；新增列 nullable / 带默认。

## 5. 分期计划

- **P1 — 创建闭环 + 列表卡片化**（KB-B + KB-C）
  - 列表页 → Dify 卡片网格（icon + 名 + 文档/分段数 + 状态 + 描述）+「创建知识库」入口卡。
  - `/kbs/create` 多步向导：① 基本信息 + 上传文件（复用 upload-zone，先存客户端）② 分段与清洗预览（复用 chunking-preview）③ 检索设置（recall_mode/top_k/阈值/rerank）④ 创建 KB → 导入文件 → 进度 → 完成跳详情。
- **P2 — 详情页 Dify 左导航重排 + 文档列表增强**（KB-D）
  - 左导航：文档 / 召回测试 / 设置（评测·一致性·集合收进设置或二级）。
  - 文档列表：状态徽章 + 启停开关 + 排序（命中/日期/字数）+ 状态筛选 + 批量（启停/删/重建/改元数据）+「添加文档」入口（复用向导步骤）。
  - 设置页重排：基本信息 + 检索设置 + 分块默认。
- **P3 — 段落（chunk）级交互（文档交互核心）**
  - 后端：chunk 编辑 / 新增 / 删除 / 启停 + 命中数；前端：段落列表（左）+ 详情（右）查看/编辑/新增/启停 + 段内搜索；接上 `chunk-card` 的 onSave。
- **P4 — 分段质量（文档质量核心）**
  - parent-child 分层分块 + QA 分块 + 文本清洗规则（去多余空白/URL/邮箱）；分段预览 + 创建向导加这些选项；父子块在段落管理里可视化。
- **P5 — 元数据字段体系**
  - dataset 级字段定义（string/number/date/select）+ 每文档值编辑 + 批量改 + 检索过滤。
- **P6 —（可选/后续）**：数据源扩展、权限、图标、外部 KB、成本预估、图片查询。

每期：ruff/tsc/eslint + 浏览器 e2e 截图存证（建库→上传→分段→检索全链路）。

## 6. 风险

- **分层分块 + chunk schema 变更**最重（P4），牵动 ingest pipeline、检索、reindex；先在 P3 把 chunk CRUD/启停打牢再上分层。
- 创建与导入合一的向导要处理"先建库后上传"的客户端暂存 + 失败回滚（建库成功但上传失败 → 库已建，进详情续传）。
- 元数据过滤要进检索 SQL（pgvector + JSONB 过滤），注意索引。
- e2e 需要真实 embedding + 有数据的库，dev 环境凭据要可用。

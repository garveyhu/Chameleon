# Chameleon 项目目录结构

**适用**：新成员上手 / Code review / PR 选位置 / 重构决策

本文档是项目**布局规约**的事实说明，回答 "这个新文件该放哪？" 的问题。
所有结构必须与 [coding-standards](../../.claude/CLAUDE.md) § 1.2 / 2.1 一致；
当文档与代码冲突时，**以代码为准并立刻更新文档**。

Chameleon 是开源 LLMOps 一站式平台：多源 AI 聚合 + 工作流编排 + RAG 知识库 +
Trace/Eval 可观测 + 多 agent 协同 + 可嵌入 SDK。后端单租户，模型聚合 / 路由
交给外部 oneapi。

---

## 0. 顶层全景（7 个一级目录）

```
Chameleon/
├── backend/        Python / FastAPI 后端（uv workspace 多包 monorepo，10 包严格分层）
├── frontend/       React 19 / TS 前端（Vite + Tailwind v4 + Radix + ReactFlow）
├── sdk/            对外 SDK（Python + TypeScript）
├── docker/         三区 Docker 部署（images / containers / scripts）
├── docs/           中英文文档 + 路线 + ADR + competitive 分析
├── scripts/        仓库级运维 / benchmark / seed 脚本
├── CHANGELOG.md    Keep a Changelog 格式 + SemVer
└── README.md       项目入口（README.en.md 英文版）
```

**红线**：
- ⛔ 不在顶层散文件（除 README / CHANGELOG / .gitignore / .python-version 等纯元数据）
- ⛔ 不创建 `src/` 在顶层（与 `backend/` 或 `frontend/src/` 混淆）—— 已删过 2 次孤儿
- ⛔ 不创建 `backend/backend/` 这种嵌套（之前出现过，已清）

---

## 1. backend/ —— Python 后端（uv workspace，10 包）

依赖方向严格单向，由 **import-linter** 强制（pyproject `[[tool.importlinter.contracts]]` 2 契约 GREEN）：

```
core ← data ← integrations ← engine ← (providers / api / system / app / agents / agentkit)
```

- **基座四层**单向：`core ← data ← integrations ← engine`（禁反向 / 越层）。
- core 保持**纯抽象**：禁 import `sqlalchemy` / `langchain` 系。
- 上层应用包（providers / api / system / app / agents / agentkit）依赖 engine 及其下游。

```
backend/
├── alembic.ini                数据库迁移配置（PG 默认）
├── pyproject.toml             workspace root（members + import-linter 契约 + ruff）
├── uv.lock                    锁定依赖（uv sync 自动维护）
│
├── chameleon-core/            纯协议 + 数据结构 + observe 协议（pydantic-only，禁 sqlalchemy/langchain）
│   └── src/chameleon/core/
│       ├── api/               Result 响应封装 + 全局异常 + SSE 协议
│       ├── base/              基础数据结构 / mixin
│       ├── components/        通用组件
│       ├── config/            inventory 具名 getter + settings + system_settings schema
│       ├── embedding/         embedding client 抽象
│       ├── function/          function-call helpers
│       ├── observe/           ContextVar 上下文 + sink 协议（trace 落库切面）
│       ├── plugins/           插件协议
│       ├── sandbox/           sandbox runtime 协议
│       ├── schema/            JSON Schema 引擎
│       ├── tools/             Tool 抽象
│       └── vector/            向量操作协议
│
├── chameleon-data/            ORM + infra + utils（持久化层）
│   └── src/chameleon/data/
│       ├── models/            SQLAlchemy 2.0 async ORM（agent / api_key / graph /
│       │                      session / knowledge / kb_collection / model_def /
│       │                      provider / eval_* / score / task / human_input ...）
│       ├── infra/             db / redis / object_store / jwt / auth / logger
│       └── utils/             snowflake / passwords / crypto / convert / spans / tokenizer
│
├── chameleon-integrations/    厂商 / 外部实现（落地各类协议）
│   └── src/chameleon/integrations/
│       ├── llms/              LLM 工厂 + base（厂商 client）
│       ├── vector/            pgvector / chroma + factory
│       ├── bridges/           langchain / langgraph 桥
│       ├── observe/           observe 落库 handler（call_logs）+ graph_spans + aggregator
│       ├── tools/             内置 tool 实现 + registry
│       ├── plugins/           plugins registry + 签名 + builtins
│       └── knowledge.py       knowledge 集成入口
│
├── chameleon-engine/          编排层（graph 引擎 / 检索 / eval / a2a / jobs）
│   └── src/chameleon/engine/
│       ├── graph/             GraphEngine + node_base + registry + variables
│       │   └── nodes/         LLM / KB / Tool / HTTP / Code(沙箱) / Template /
│       │                      Classifier(意图分类) / Aggregator / Answer / Assign /
│       │                      If-Else / Iteration / Parallel / AgentDebate / HumanInput
│       ├── retrieval/         HybridPipeline + expander + rerankers + VLM caption
│       ├── eval/              eval algorithms
│       ├── agent/             a2a 协议
│       └── jobs/              异步 job 编排
│
├── chameleon-providers/       provider 抽象 + 具体 provider（每个独立子包）
│   ├── base/                  ProviderBase 协议 / types / registry
│   ├── local/                 进程内 BaseAgent 本地 runtime
│   ├── dify/                  Dify app 适配
│   ├── fastgpt/               FastGPT 知识库 + workflow 适配
│   └── graph/                 工作流即 agent（graph 作为 source='graph' 的 provider）
│
├── chameleon-agentkit/        进程内 agent SDK
│   └── src/chameleon/agentkit/
│       ├── _decorator.py      @agent 装饰器（ctx 隐式拿模型/KB/trace）
│       ├── _runtime.py        进程内运行时 + entry-points 发现
│       └── _spec.py           多具名模型槽 + 配置 Schema→自动表单
│
├── chameleon-agents/          业务级本地 agent（每个独立子包）
│   ├── examples/              echo / rag_qa / triage 示例
│   └── qwen_chat/             生产示例：Qwen 多轮对话
│
├── chameleon-api/             对外 AI 服务 API（公开面）
│   └── src/chameleon/api/
│       ├── agent/             /v1/invoke + /v1/info（Dify 风，key 即应用身份）+ stream
│       ├── sessions/          /v1/sessions（ChatSession + 分支对话树）
│       ├── knowledge/         /v1/kb 摄入 + 检索 + chunkers + parsers + hit_test
│       ├── embed/             /v1/embed widget 调用 + 嵌入式 session
│       ├── files/             /v1/files presigned upload
│       ├── task/              /v1/tasks 异步任务
│       ├── otel/              /v1/otel OTLP HTTP/JSON 摄入
│       └── openai/            OpenAI 兼容端点（/v1/chat/completions）
│
├── chameleon-system/          内部 admin 管理 API（权限受控）
│   └── src/chameleon/system/
│       ├── auth/              /v1/auth JWT 登录 / 改密 / RBAC
│       ├── api_key/           /v1/admin/api-keys（作用域 app / agent / kb）
│       ├── agents/            /v1/admin/agents 应用（伞形）注册管理
│       ├── app_templates/     /v1/admin/app-templates 应用模板
│       ├── providers/         /v1/admin/providers
│       ├── models/            /v1/admin/models + pricing 价目表
│       ├── pricing/           cost 计算 + 价目表 effective_from
│       ├── kbs/               /v1/admin/kbs + collections + 一致性扫描
│       ├── datasets/          /v1/admin/datasets + PII + bulk import
│       ├── eval_jobs/         /v1/admin/eval-jobs 评测任务
│       ├── eval_templates/    /v1/admin/eval-templates
│       ├── graphs/            /v1/admin/graphs 工作流 CRUD + 版本化 + 智能体密钥
│       ├── plugins/           /v1/admin/plugins 插件管理
│       ├── marketplace/       /v1/admin/marketplace 插件市场
│       ├── tools/             /v1/admin/tools tool 实例配置
│       ├── schemas/           /v1/admin/schemas JSON Schema 调试
│       ├── scores/            /v1/admin/scores feedback API
│       ├── search/            /v1/admin/search 全局搜索
│       ├── dashboard/         /v1/admin/dashboard 含 cost 多维聚合
│       ├── playground/        /v1/admin/playground 调试入口
│       ├── embed_configs/     /v1/admin/embed-configs widget 嵌入配置
│       ├── session_files/     /v1/admin/session-files 会话文件
│       ├── audit_logs/        /v1/admin/audit-logs 审计
│       ├── settings/          /v1/admin/settings system_settings 通用配置
│       ├── users/             /v1/admin/users 用户 CRUD + 密码
│       ├── roles/             /v1/admin/roles RBAC role
│       ├── permissions/       /v1/admin/permissions
│       ├── admin/             call_logs 查询 + providers 健康
│       └── seed/              启动期 RBAC + admin + models / agents 初始化
│
├── chameleon-app/             薄 FastAPI 启动器
│   └── src/chameleon/app/     main.py（装配 + lifespan + 中间件 + DI 注入）+ cli.py
│
├── config/                    业务参数文件（不入 git 的部分由 .gitignore 兜）
│   ├── example/               配置模板（入 git）
│   ├── .env                   ⛔ 不入 git：敏感凭据
│   ├── chameleon.json         ⛔ 不入 git：业务参数（DB 化后由 system_settings 覆盖）
│   ├── model.json             ⛔ 不入 git：providers + models + cases
│   └── component.json         ⛔ 不入 git：database / redis / object_store
│
├── migrations/                Alembic forward-only
│   ├── env.py
│   └── versions/              hash / 语义混合命名（如 p{阶段}{子}_{描述}.py）
│
├── tests/                     跨包集成 / e2e 测试
├── resources/                 内部缓存（gitignore）
└── logs/                      运行时日志（gitignore）
```

**红线（详见 [coding-standards](../../.claude/CLAUDE.md) § 1）**：
- ⛔ 反向 / 越层依赖（import-linter 会拦：`core ← data ← integrations ← engine` 单向）
- ⛔ chameleon-core 里 import `sqlalchemy` / `langchain`（core 保持纯抽象）
- ⛔ 业务包之间不互相依赖；共用能力下沉到下游基座层
- ⛔ API 层零业务（参数校验后立刻调 service）
- ⛔ service 不返 ORM Model（必须转 Pydantic DTO）
- ⛔ 仅 GET + POST，无 PUT / DELETE / PATCH
- ⛔ 所有响应必须包 `Result.ok(...)` / `Result.fail(...)`
- ⛔ 不修改已发布 alembic migration（forward-only）

---

## 2. frontend/ —— React / TS 前端

技术栈：React 19 + Vite + TS strict + Tailwind v4 + Radix + TanStack Query + Zustand + ReactFlow。
导航 IA = **4 域**（工作台 / 知识库 / 观测 / 设置），顶栏切域 + 左侧无边二级导航，
单一数据源在 `src/core/components/layout/nav-config.ts`。

```
frontend/
├── package.json               yarn + Vite + React 19 + TS + Tailwind v4 + Radix
├── vite.config.ts             alias @/ → src/
├── tsconfig*.json             strict + path alias
├── eslint.config.js / postcss.config.js
│
├── index.html                 admin 入口（/）
├── public/                    静态资源
│
├── embed/                     widget 独立 bundle（shadow DOM）
│   └── src/                   widget 入口 + runtime
│
├── dist/                      构建产物（gitignore）
│
└── src/
    ├── App.tsx / main.tsx     应用入口
    ├── assets/styles/         主题 CSS variables + Tailwind extend
    ├── router/                React Router 配置（按模块 routes.ts 自动收集）
    │
    ├── core/                  共享基础设施层（无业务知识）
    │   ├── components/
    │   │   ├── ui/            Radix 包装 + primitive（Button / Modal / Badge ...）
    │   │   ├── form/          JSON Schema 动态表单
    │   │   │   └── widgets/   各 field 类型 widget
    │   │   ├── layout/        MainLayout + top-bar(域) + secondary-nav + nav-config
    │   │   ├── command/       Cmd+K command palette
    │   │   ├── chat/          通用对话组件
    │   │   ├── common/        EmptyState / NavProgressBar / PermissionGuard
    │   │   └── table/         DataTable + SectionCard + Pagination + Toolbar
    │   ├── constants/         路由表 / 主题表 / 全局常量
    │   ├── hooks/             跨页面通用 hook
    │   ├── i18n/              react-i18next + locales/{zh-CN,en-US}.json
    │   ├── lib/               cn / format / request / toast / confirm
    │   ├── services/          通用 HTTP service helper
    │   ├── stores/            Zustand store（auth / preferences / nav-pending / chat / kb / trace / workflow）
    │   └── types/             跨模块共用 TS 类型
    │
    ├── system/                业务模块层（每个模块自包含）
    │   每个模块子目录约定：
    │       {module}/
    │         routes.ts        模块路由声明（被 src/router 自动收集）
    │         types/           本模块 TS 类型
    │         services/        HTTP service（只能在这里 fetch / axios）
    │         components/      仅本模块用组件
    │         pages/           路由级页面
    │         hooks/           ⌗ 可选：仅本模块用 hook（拆复杂页面时）
    │
    │   模块按 4 导航域归属（见 nav-config.ts）：
    │   【工作台】 agents（应用，伞形）· graphs（ReactFlow 工作流编辑器）·
    │             conversations（对话树 / 分支）· embed_configs · embed_iframe
    │   【知识库】 kbs（含 collections / 一致性 / hit-test）· session_files
    │   【观测】   dashboard（+ cost）· traces（ObservationTree）·
    │             playground · datasets · eval_jobs · audit_logs · call_logs（并入 trace）
    │   【设置】   providers · models · plugins · marketplace ·
    │             api_keys（作用域 app/agent/kb）· users · roles · settings
    │   【辅助】   auth（登录 / 改密）· search（Cmd+K）· files · dev_schemas
    │
    └── api-docs/              独立接口文档站（零业务耦合，可整目录拆出单独部署）
        ├── routes.ts
        ├── pages/             agent / kb 接口文档页 + docs station
        ├── components/ · registry/ · types/
```

**红线（详见 [coding-standards](../../.claude/CLAUDE.md) § 2）**：
- ⛔ pages / components / hooks 里禁止 `fetch` / `axios.*`（统一在 services/）
- ⛔ 业务逻辑不下沉到展示组件（接 props 出 UI 之外的事都不做）
- ⛔ Prop drilling 超两层上 Context 或 Zustand
- ⛔ 跨目录 import 用 `@/`（不写 `../../../`）
- ⛔ 硬编码颜色 / 字号 / 间距字面量（走 Tailwind + 主题 token）
- ⛔ 不用 `React.FC`（吞 children 类型）
- ⛔ 单 `.tsx` > 500 行该拆（抽 hook / 子组件）

---

## 3. sdk/ —— 对外 SDK

```
sdk/
├── python/                    pip install chameleon-sdk
│   ├── pyproject.toml
│   ├── README.md
│   └── chameleon_sdk/         httpx sync + async client + @trace / patch_openai / patch_all
│
└── typescript/                npm i @chameleon/sdk
    ├── package.json
    ├── tsconfig.json
    ├── README.md
    └── src/                   ChameleonClient + trace helpers（OTLP HTTP 上报）
```

**红线**：
- ⛔ Python / TS 同步发版（API 概念一致）
- ⛔ 不依赖 backend 私有模块（只走 public REST / OTLP）

---

## 4. docker/ —— 三区部署

```
docker/
├── images/                    所有 Dockerfile + nginx.conf + entrypoint + .env.example
├── containers/                docker-compose 编排
│   ├── docker-compose.yml     本地 dev 全栈
│   ├── initdb/                PG 初始化 SQL
│   ├── prod/                  生产 compose + 环境隔离
│   │   ├── docker-compose.yml
│   │   └── initdb/
│   └── data/                  ⛔ 不入 git：运行时数据卷
└── scripts/                   build-images.sh / push-images.sh / run-local.sh / stop-local.sh
```

**红线（详见 [docker-best-practices](../../.claude/CLAUDE.md)）**：
- ⛔ containers/data/ 永不入 git（数据库文件）
- ⛔ images/.env / containers/.env / scripts/.registry.env 永不入 git（凭据）
- ⛔ 多镜像拆分（base + code + ui + venv + models）—— 不打成一个大包

---

## 5. docs/ —— 文档体系

```
docs/
├── 主入口（中英文都引用，谨慎改路径）
│   ├── architecture.md        架构总览（mermaid 分层 / 数据流 / schema 关系）
│   ├── quickstart.md          5 分钟跑通
│   ├── getting-started.md     上手指南（含配置 / 启动）
│   ├── operations.md          运维手册
│   ├── cli.md                 chameleon CLI 命令
│   ├── providers.md           Provider 协议说明
│   ├── extension-guide.md     扩展开发指南
│   ├── api-reference.md       接口参考
│   ├── embed-architecture.md  嵌入式 widget 架构
│   └── embed-integration-guide.md  嵌入接入指南
│
├── zh/                        中文文档（深入版）
│   ├── architecture.md
│   ├── admin-guide.md
│   ├── api-reference.md
│   ├── deployment.md
│   └── project-structure.md   ← 本文档
│
├── en/                        English deep-dive docs（architecture / admin-guide / api-reference / deployment）
│
├── adr/                       Architecture Decision Records（每张新表 / 大决策一份）
│
├── competitive/               5 个 OSS 标杆分析（永久参考）
│   ├── dify-analysis.md
│   ├── fastgpt-analysis.md
│   ├── langfuse-analysis.md
│   ├── lobechat-analysis.md
│   └── one-api-analysis.md
│
├── plans/                     阶段路线 + detail sub-plan（YYYY-MM-DD-描述.md）
│
├── release/                   每 v-release 配套（migration / screenshots / benchmark）
│
└── sdk/                       SDK 文档（Python / TypeScript）
    ├── python.md
    └── typescript.md
```

**红线**：
- ⛔ 主入口 .md 不能随意挪位置（CHANGELOG / README / 多处 plan 都引用）
- ⛔ 改 ADR / migration / benchmark 文档不能改文件名（外链已固化）
- ⛔ plans/{date}-*.md 命名规则：`YYYY-MM-DD-描述.md`

---

## 6. scripts/ —— 仓库级脚本

```
scripts/
├── bench_v1.py                microbench（fuse_rrf / HybridPipeline / RAGAS）
├── bench_retrieval.py         检索管线基准
├── check-orm-db-drift.py      ORM ↔ DB schema 漂移检查
├── seed_demo_data.py          demo 数据 seed（dashboard / cost / trace 不空）
└── setup_multi_agent.sh       多 agent 环境准备
```

**规约**：
- 脚本必须**零外部依赖**（不引 loguru / rich 等，用 print）
- 用 `cd backend && uv run python ../scripts/{name}.py` 跑
- 幂等（多次跑结果一致）
- 不进 system/seed 启动序（避免污染生产）

未来脚本变多时按用途分子目录：
```
scripts/
├── bench/                     性能基准
├── dev/                       开发期辅助（含 seed）
├── ops/                       运维（备份 / 巡检）
└── ci/                        CI/CD 工具
```

---

## 7. 根目录文件清单

| 文件 | 用途 | 红线 |
|------|------|------|
| `README.md` / `README.en.md` | 项目入口（中英） | 改主版本号时同步两份 |
| `CHANGELOG.md` | Keep a Changelog + SemVer | 每 PR Unreleased 加一行；发版时归档 |
| `.gitignore` | git 排除规则 | 改前先看是否有 secrets 在 untracked |
| `.dockerignore` | docker build context 排除 | 与 .gitignore 联动 |
| `.python-version` | pyenv / asdf 版本提示（3.12） | uv 也读这个 |
| `.github/` | CI workflows | PR / push 触发；改要懂 GitHub Actions |
| `.vscode/` | 共享 IDE 配置 | 不入个人偏好（用 settings.json 模板） |

---

## 8. 决策框架（"这个新文件该放哪？"）

```mermaid
graph TD
    classDef back fill:#2B6CB0,stroke:#1E5090,stroke-width:2px,color:#fff
    classDef front fill:#48BB78,stroke:#38A169,stroke-width:2px,color:#fff
    classDef doc fill:#ED8936,stroke:#C66A32,stroke-width:2px,color:#fff

    A([要加新文件]) --> B{后端 / 前端 / 文档?}

    B -->|后端| C{这是什么?}
    C -->|纯协议 / 数据结构| D[chameleon-core/]:::back
    C -->|ORM / infra / utils| E[chameleon-data/]:::back
    C -->|厂商 / 外部实现| F[chameleon-integrations/]:::back
    C -->|graph / 检索 / eval 编排| G[chameleon-engine/]:::back
    C -->|provider 适配| PR[chameleon-providers/]:::back
    C -->|对外 AI 服务 API| H1[chameleon-api/]:::back
    C -->|admin 管理 API| H2[chameleon-system/]:::back

    B -->|前端| I{通用 / 业务?}
    I -->|通用 无业务知识| J[frontend/src/core/]:::front
    I -->|业务模块| K[frontend/src/system/{module}/]:::front
    K --> L{HTTP / UI / 页面?}
    L -->|HTTP 调用| M[services/]:::front
    L -->|UI 组件| N[components/]:::front
    L -->|路由级页面| O[pages/]:::front

    B -->|文档| P{阶段 / 决策 / 手册?}
    P -->|阶段计划| Q[docs/plans/]:::doc
    P -->|架构决策| R[docs/adr/]:::doc
    P -->|用户手册| S[docs/zh/ or docs/en/]:::doc
```

> 选位置时先认**依赖方向**：新代码只能依赖比它更下游的层（`core ← data ← integrations ← engine ← 应用包`）。
> 若发现需要反向依赖，说明放错了层，import-linter 会在 CI 拦下。

---

## 9. 变更本文档

本文档随项目演进。每次 PR 涉及新增 / 删除 / 移动**模块级**（不是单文件）改动时，**必须**同步更新本文档：
- 新增 backend 子包 → § 1 加一行
- 新增 frontend 业务模块 → § 2 域分组里加，并在 `nav-config.ts` 挂到对应导航域
- 新增 sdk 语言 → § 3 加块
- 新增 docs 子目录 → § 5 加块
- 修改顶层目录 → § 0 + § 8 决策图都改

PR description 显式声明 "更新 project-structure.md"。

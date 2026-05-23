# Chameleon 项目目录结构

**版本**：v1.0（2026-05-24 整理）
**适用**：新成员上手 / Code review / PR 选位置 / 重构决策

本文档是项目**布局规约**的事实说明，回答 "这个新文件该放哪？" 的问题。
所有结构必须与 [coding-standards](../../.claude/CLAUDE.md) § 1.2 / 2.1 一致；
当文档与代码冲突时，**以代码为准并立刻更新文档**。

---

## 0. 顶层全景（7 个一级目录）

```
Chameleon/
├── backend/        Python / FastAPI 后端（uv workspace 多包 monorepo）
├── frontend/       React / TS 前端（Vite + Tailwind + Antd）
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

## 1. backend/ —— Python 后端（uv workspace）

```
backend/
├── alembic.ini                数据库迁移配置（PG 默认）
├── pyproject.toml             workspace root（声明 6 个 member 子包）
├── uv.lock                    锁定依赖（uv sync 自动维护）
│
├── chameleon-core/            基础设施 + ORM + 共享工具（所有上游依赖它）
│   └── src/chameleon/core/
│       ├── agent/             A2A 协议 + AgentRunner（P20.4）
│       ├── api/               Result/PageResult 响应封装 + 全局异常 handler
│       ├── base/              SoftDeleteMixin / TimestampMixin / snowflake id
│       ├── components/        通用组件（如 diskcache wrapper）
│       ├── config/            inventory 具名 getter（db_url / minio_config 等）
│       ├── embedding/         embedding client 抽象
│       ├── eval/              RAGAS 4 算子 + judge helpers（P21.2）
│       ├── function/          tool function-call helpers
│       ├── graph/             Node 基类 + 节点实现 + GraphEngine（v1.1 重写）
│       ├── infra/             db / redis / object_store / sse 协议
│       ├── models/            SQLAlchemy 2.0 ORM（30+ 张表）
│       ├── observe/           record_call / Observation 嵌套 / quota
│       ├── plugins/           插件协议 + Ed25519 签名（P20.2）
│       ├── retrieval/         HybridPipeline 6 步 + Reranker + VLM（P22.4）
│       ├── routing/           Channel / Ability 路由 + failover
│       ├── sandbox/           Docker / Mock runtime（P20.1）
│       ├── schema/            JSON Schema 引擎（F1）
│       ├── tools/             Tool 抽象 + 5 内置 tool
│       ├── utils/             snowflake / passwords / time / ...
│       └── vector/            pgvector 操作
│
├── chameleon-providers/       Provider 协议实现（base 抽象 + 4 个具体）
│   ├── base/                  ProviderBase / Streaming / ContentBlock
│   ├── local/                 native Python agent 本地 runtime
│   ├── dify/                  Dify app 适配
│   └── fastgpt/               FastGPT 知识库 + workflow 适配
│
├── chameleon-agents/          示例 + 实战 agent
│   ├── examples/
│   │   ├── echo_langgraph/    LangGraph 风格示例
│   │   ├── echo_native/       native ContentBlock 多模态示例
│   │   └── echo_runnable/     Runnable 协议示例
│   └── qwen_chat/             生产示例：Qwen 多轮对话
│
├── chameleon-api/             业务 API（B2B 调用入口）
│   └── src/chameleon/api/
│       ├── agent/             /v1/agent/invoke + /v1/agent/stream
│       ├── conversation/      会话管理（含对话树 P21.4）
│       ├── embed/             /v1/embed/* widget 调用
│       ├── files/             MinIO presigned upload（P19.4）
│       ├── knowledge/         KB 摄入 + 检索 + chunkers
│       │   ├── chunkers/      FAQ / Wiki / API / generic 4 策略
│       │   └── parsers/       PDF / Word / HTML 解析
│       ├── otel/              OTLP HTTP/JSON 摄入端点（P22.2）
│       └── task/              异步任务调度
│
├── chameleon-system/          管理后台 API（admin 视角，权限受控）
│   └── src/chameleon/system/
│       ├── admin/             call_logs 查询 + providers 健康监控
│       ├── api_key/           API key CRUD（生产 / 测试 / 临时）
│       ├── abilities/         Ability 矩阵 CRUD（A1）
│       ├── agents/            Agent 注册管理
│       ├── apps/              App + AppAgent 授权
│       ├── audit_logs/        11 维审计（P22.1）
│       ├── auth/              JWT 登录 / 改密 / RBAC 检查
│       ├── channels/          Channel CRUD + 健康状态
│       ├── datasets/          Dataset + PII + 采样 + bulk import（P21.1）
│       ├── dashboard/         /v1/admin/dashboard/* 含 cost 多维聚合
│       ├── embed_configs/     widget 嵌入配置
│       ├── eval_templates/    EvalTemplate + version 自增（P21.2）
│       ├── graphs/            Workflow CRUD + 版本化 + runner（P22.3）
│       ├── kbs/               KB CRUD + collections + 一致性扫描（P21.3）
│       ├── marketplace/       插件市场 registry + 应用模板（P20.2 / P22.5）
│       ├── models/            Model + PricingTier 价目表
│       ├── playground/        admin 调试入口（不写 call_log）
│       ├── plugins/           插件管理 + manifest + reload（P19.2）
│       ├── pricing/           cost 计算 + 价目表 effective_from
│       ├── providers/         Provider 管理
│       ├── roles/             RBAC role CRUD
│       ├── scores/            /v1/admin/scores feedback API
│       ├── seed/              启动期 RBAC + admin + models / agents 初始化
│       ├── settings/          system_settings 通用配置
│       ├── tools/             Tool 实例配置（admin 视角）
│       ├── traces/            Trace 详情 API（call_log tree）（P22.3）
│       ├── users/             User CRUD + 密码管理
│       └── workspaces/        多租户 + Quota + Members（P19.3）
│
├── chameleon-app/             FastAPI 入口（薄壳）
│   └── src/chameleon/app/     lifespan + 中间件 + router 装配
│
├── config/                    业务参数文件（不入 git 的部分由 .gitignore 兜）
│   ├── example/               配置模板（入 git）
│   ├── .env                   ⛔ 不入 git：敏感凭据
│   ├── chameleon.json         ⛔ 不入 git：业务参数（DB 化后由 system_settings 覆盖）
│   ├── model.json             ⛔ 不入 git：providers + models + cases
│   ├── component.json         ⛔ 不入 git：database / redis / minio
│   └── agents.yaml            ⛔ 不入 git：外部 agent 注册
│
├── migrations/                Alembic forward-only
│   ├── env.py
│   └── versions/              语义命名：p{阶段}{子}_{描述}.py
│
├── tests/                     跨包集成 / e2e 测试
├── resources/                 diskcache 等内部缓存（gitignore）
└── logs/                      运行时日志（gitignore）
```

**红线（详见 [coding-standards](../../.claude/CLAUDE.md) § 1）**：
- ⛔ chameleon-core 不能反向依赖任何 chameleon-{api,system,app,...}
- ⛔ 业务包之间不互相依赖；共用能力下沉到 core
- ⛔ API 层零业务（参数校验后立刻调 service）
- ⛔ service 不返 ORM Model（必须转 Pydantic DTO）
- ⛔ 仅 GET + POST，无 PUT / DELETE / PATCH
- ⛔ 所有响应必须包 `Result.ok(...)` / `Result.fail(...)`
- ⛔ 不修改已发布 alembic migration（forward-only）

---

## 2. frontend/ —— React / TS 前端

```
frontend/
├── package.json               yarn + Vite + React + TS + Tailwind + Antd
├── vite.config.ts             alias @/ → src/
├── tsconfig*.json             strict + path alias
├── eslint.config.js / postcss.config.js
│
├── index.html                 admin 入口（/）
├── public/                    静态资源
│
├── embed/                     widget 独立 bundle（< 30KB gz；shadow DOM）
│   └── src/                   widget 入口 + runtime
│
├── dist/                      构建产物（gitignore）
│
└── src/
    ├── assets/styles/         主题 CSS variables + Tailwind extend
    │
    ├── router/                React Router 配置
    │
    ├── core/                  基础设施层（无业务知识）
    │   ├── components/
    │   │   ├── ui/            Antd 包装 + shadcn 风格 primitive（Button / Modal / Badge ...）
    │   │   ├── form/          JSON Schema 动态表单（F1）
    │   │   │   └── widgets/   各 field 类型 widget
    │   │   ├── layout/        MainLayout + Sidebar（waveflow 风格）
    │   │   ├── command/       Cmd+K command palette
    │   │   ├── common/        EmptyState / NavProgressBar / PermissionGuard
    │   │   └── table/         DataTable + SectionCard + Pagination + Toolbar
    │   ├── constants/         路由表 / 主题表 / 全局常量
    │   ├── hooks/             跨页面通用 hook
    │   ├── i18n/              react-i18next + locales/{zh-CN,en-US}.json
    │   ├── lib/               cn / format / request / toast / confirm
    │   ├── services/          通用 HTTP service helper
    │   ├── stores/            Zustand store（auth / preferences / workspace / nav-pending）
    │   └── types/             跨模块共用 TS 类型
    │
    └── system/                业务模块层（28 模块）
        每个模块 4 子目录约定：
            {module}/
              routes.ts        模块路由声明（被 src/router 自动收集）
              types/           本模块 TS 类型
              services/        HTTP service（只能在这里 fetch / axios）
              components/      仅本模块用组件
              pages/           路由级页面
              hooks/           ⌗ 可选：仅本模块用 hook（拆复杂页面时）

        当前模块清单（按 sidebar 分组）：
        ├── dashboard/         仪表盘 + cost 子页
        ├── workspaces/        多租户切换 + members + quota
        │
        【AI 配置】
        ├── agents/            智能体管理
        ├── providers/         Provider 管理
        ├── channels/          Channel CRUD + 健康
        ├── abilities/         Ability 矩阵
        ├── models/            模型管理
        ├── kbs/               知识库（含 collections / 一致性 / hit-test tab）
        ├── playground/        多列调试 + 多模态上传
        ├── conversations/     对话树 + 分支切换 + regenerate
        ├── graphs/            React Flow workflow 编辑器
        ├── datasets/          Dataset + PII + bulk import
        ├── eval_jobs/         评测任务 cron + alert
        ├── plugins/           插件管理
        ├── marketplace/       插件市场 + 应用模板
        ├── embed_configs/     widget 嵌入配置
        │
        【应用 & 调用】
        ├── apps/              应用 + API key
        ├── call_logs/         旧调用日志（v1.1+ 合并到 traces）
        ├── traces/            Trace 详情页 ObservationTree
        ├── users/             用户管理
        ├── roles/             角色 + 权限
        │
        【系统】
        ├── audit_logs/        审计日志
        ├── settings/          系统配置
        ├── auth/              登录 / 改密页
        │
        【辅助】
        ├── search/            Cmd+K 全局搜索
        ├── files/             文件管理
        ├── embed_iframe/      widget iframe 视图
        └── dev_schemas/       开发期 schema 调试
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
│   └── chameleon_sdk/         Client + AsyncClient + Trace/Span 链式 + decorators
│
└── typescript/                npm i @chameleon/sdk
    ├── package.json
    ├── tsconfig.json
    ├── README.md
    └── src/                   ChameleonClient + withTrace / withSpan
```

**红线**：
- ⛔ v1.0+ 走 deprecation policy（保留 1 minor 版本）
- ⛔ Python / TS 同步发版（API 概念一致）
- ⛔ 不依赖 backend 私有模块（只走 public REST/OTLP）

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
│   └── extension-guide.md     扩展开发指南
│
├── zh/                        中文文档（深入版）
│   ├── architecture.md
│   ├── admin-guide.md
│   ├── api-reference.md
│   ├── deployment.md
│   └── project-structure.md   ← 本文档
│
├── en/                        English deep-dive docs
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
├── plans/                     阶段路线 + detail sub-plan
│   ├── 2026-05-23-chameleon-master-plan.md   ← 12 月主路线（48 项 feature）
│   ├── 2026-05-23-p{17..22}-detail.md        ← P17-P22 已 ship
│   ├── 2026-05-23-v1.0-deep-audit.md         ← v1.0 深度审计（vs 5 OSS）
│   └── 2026-05-24-p23-detail.md              ← v1.1 待 ship
│
├── release/                   每 v-release 配套
│   ├── v0.{3..7}-migration.md / v1.0-migration.md   升级步骤
│   ├── v0.{6,7}-screenshots/  Chrome MCP 截图 + VERIFICATION.md
│   └── v1.0-benchmark.md      microbench 结果
│
└── sdk/                       SDK 文档（Python / TypeScript）
    ├── python.md
    └── typescript.md
```

**红线**：
- ⛔ 主入口 7 个 .md 不能挪位置（CHANGELOG / README / 多处 plan 都引用）
- ⛔ 改 ADR / migration / benchmark 文档不能改文件名（外链已固化）
- ⛔ plans/{date}-*.md 命名规则：`YYYY-MM-DD-描述.md`

---

## 6. scripts/ —— 仓库级脚本

```
scripts/
├── bench_v1.py                v1.0 microbench（fuse_rrf / HybridPipeline / RAGAS）
└── seed_demo_data.py          demo 数据 seed（dashboard / cost / trace 不空）
```

**规约**：
- 脚本必须**零外部依赖**（不引 loguru / rich 等，用 print）
- 用 `cd backend && uv run python ../scripts/{name}.py` 跑
- 幂等（多次跑结果一致）
- 不进 system/seed/runner.py 启动序（避免污染生产）

未来加脚本时按用途分子目录：
```
scripts/
├── bench/                     性能基准
├── dev/                       开发期辅助（含 seed）
├── ops/                       运维（备份 / 巡检）
└── ci/                        CI/CD 工具
```
（当前 2 个文件不分类，>= 4 个时分。）

---

## 7. 根目录文件清单

| 文件 | 用途 | 红线 |
|------|------|------|
| `README.md` / `README.en.md` | 项目入口（中英） | 改主版本号时同步两份 |
| `CHANGELOG.md` | Keep a Changelog + SemVer | 每 PR Unreleased 加一行；发版时归档 |
| `.gitignore` | git 排除规则 | 改前先看是否有 secrets 在 untracked |
| `.dockerignore` | docker build context 排除 | 与 .gitignore 联动 |
| `.python-version` | pyenv / asdf 版本提示（3.13） | uv 也读这个 |
| `.github/` | CI workflows | PR / push 触发；改要懂 GitHub Actions |
| `.vscode/` | 共享 IDE 配置 | 不入个人偏好（用 settings.json 模板） |

---

## 8. 决策框架（"这个新文件该放哪？"）

```mermaid
graph TD
    A[要加新文件] --> B{后端 or 前端 or 文档?}
    B -->|后端| C{是 ORM / 工具 / 协议?}
    C -->|是| D[chameleon-core/]
    C -->|否| E{是业务 API or 管理 API?}
    E -->|业务 B2B| F[chameleon-api/]
    E -->|admin 后台| G[chameleon-system/]
    B -->|前端| H{是通用 or 业务?}
    H -->|通用 无业务知识| I[frontend/src/core/]
    H -->|业务模块| J[frontend/src/system/{module}/]
    J --> K{是 HTTP 调用?}
    K -->|是| L[services/]
    K -->|否, UI 组件| M[components/]
    K -->|页面| N[pages/]
    B -->|文档| O{阶段计划 or 决策 or 用户手册?}
    O -->|阶段| P[docs/plans/]
    O -->|架构决策| Q[docs/adr/]
    O -->|用户手册| R[docs/zh/ or docs/en/]
```

---

## 9. 变更本文档

本文档随项目演进。每次 PR 涉及新增 / 删除 / 移动**模块级**（不是单文件）改动时，**必须**同步更新本文档：
- 新增 backend 子包 → § 1 加一行
- 新增 frontend 业务模块 → § 2 sidebar 分组里加
- 新增 sdk 语言 → § 3 加块
- 新增 docs 子目录 → § 5 加块
- 修改顶层目录 → § 0 + § 8 决策图都改

PR description 显式声明 "更新 project-structure.md"。

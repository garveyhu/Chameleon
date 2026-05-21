# Chameleon

> 中文 · [English](./README.en.md)

**Chameleon** 是一套开源的 AI 服务统一聚合平台 —— 把 LangGraph / Dify / FastGPT / OpenAI 兼容厂商等多种 AI 来源统一抽象为一套 HTTP API，配套管理控制台 + 可嵌入业务网页的对话 Widget，让团队把 AI 能力当作"基础设施"管理。

**v0.1.0** · Python 3.12 · FastAPI · React 19 · PostgreSQL 16 + pgvector · Docker 一键部署

---

## ✨ 核心能力

| 能力 | 说明 |
|---|---|
| 🧩 **多源 Agent 聚合** | 本地 LangGraph 编排 · Dify / FastGPT 外调 · 通义千问等 OpenAI 兼容厂商 |
| 🎛 **管理控制台** | 用户 / 角色 / 权限 / 应用 / Provider / Model / Agent / 知识库 / 调用日志 / 审计日志 全套 admin UI |
| 🔐 **企业级鉴权** | JWT 双 Token + RBAC 三表 + AES-256-GCM 加密 provider 凭证 |
| 📚 **知识库** | pgvector + HNSW + pg_trgm，向量 + 全文双路召回 |
| 🌐 **可嵌入 Widget** | 业务网页一行 `<script>` 接入对话气泡，shadow DOM 隔离，13KB / gzip 4.8KB |
| ⚙️ **DB-driven 配置** | Provider / Model / Agent 都在 admin UI 实时改，无需重启 |
| 🐳 **一键部署** | docker compose up -d 起 5 个服务（PG + Redis + 后端 + 前端 + Nginx 反代） |

---

## 🚀 快速开始（Docker）

```bash
git clone https://github.com/your-org/chameleon.git
cd chameleon

# 1. 配置运行时密钥（**首次必改**）
cp docker/containers/.env.example docker/containers/.env
vim docker/containers/.env
#   PG_PASSWORD / REDIS_PASSWORD / CHAMELEON_JWT_SECRET / CHAMELEON_CRYPTO_KEY

# 2. 一行启动
./docker/scripts/run-local.sh

# 3. 打开 http://localhost:6006
#    首次 admin 凭据：docker/containers/data/logs/initial-admin-credentials.txt
```

详细部署文档： [docs/zh/deployment.md](./docs/zh/deployment.md) · [English](./docs/en/deployment.md)

## 📦 项目结构

```
chameleon/
├── backend/                  # FastAPI 后端（uv workspace 多包）
│   ├── chameleon-core/       # 基础设施：DB / Redis / JWT / 加密 / ORM
│   ├── chameleon-providers/  # Provider 抽象层（local / dify / fastgpt）
│   ├── chameleon-agents/     # 业务级本地 agent
│   ├── chameleon-api/        # 对外 AI 业务 API
│   ├── chameleon-system/     # admin 管理 API
│   └── chameleon-app/        # FastAPI 启动器
├── frontend/                 # React 19 管理控制台
│   ├── src/core/             # 共享基础设施（lib / components / stores / i18n / router）
│   ├── src/system/<module>/  # 业务模块（pages / services / types / routes 自包含）
│   └── embed/                # 嵌入式 Widget 独立 Vite 项目
├── docker/                   # 三区结构（images / containers / scripts）
└── docs/                     # 中英双语文档
```

## 🛠 技术栈

**后端**：Python 3.12 + uv · FastAPI · SQLAlchemy 2.0 async · PostgreSQL 16 + pgvector · Redis · loguru · pytest · ruff

**前端**：React 19 · TypeScript strict · Vite · Tailwind v4 + shadcn/ui · TanStack Query · Zustand · react-i18next

**部署**：Docker + Compose · 多阶段镜像 · BuildKit 多架构

## 📚 文档

| 文档 | 中文 | English |
|---|---|---|
| 部署指南 | [docs/zh/deployment.md](./docs/zh/deployment.md) | [docs/en/deployment.md](./docs/en/deployment.md) |
| 架构设计 | [docs/zh/architecture.md](./docs/zh/architecture.md) | [docs/en/architecture.md](./docs/en/architecture.md) |
| 管理员手册 | [docs/zh/admin-guide.md](./docs/zh/admin-guide.md) | [docs/en/admin-guide.md](./docs/en/admin-guide.md) |
| API 参考 | [docs/zh/api-reference.md](./docs/zh/api-reference.md) | [docs/en/api-reference.md](./docs/en/api-reference.md) |
| 决策记录（ADR） | [docs/adr/](./docs/adr/) | 同左 |

## 🤝 贡献

PR 欢迎！Commit 遵循 Angular 规范。

## 📄 License

[MIT](./LICENSE)

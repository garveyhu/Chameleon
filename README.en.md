# Chameleon

> English · [中文](./README.md)

**Chameleon** is an open-source AI service aggregation platform —— unifying LangGraph / Dify / FastGPT / OpenAI-compatible vendors into one HTTP API, with a full admin console and an embeddable chat widget for business websites. Manage AI capabilities as infrastructure.

**v0.1.0** · Python 3.12 · FastAPI · React 19 · PostgreSQL 16 + pgvector · One-click Docker deploy

---

## ✨ Highlights

| Capability | Detail |
|---|---|
| 🧩 **Multi-source agents** | Local LangGraph orchestration · Dify / FastGPT remote · OpenAI-compatible vendors (Qwen, etc.) |
| 🎛 **Admin console** | Users / Roles / Perms / Apps / Providers / Models / Agents / KB / Call logs / Audit |
| 🔐 **Enterprise auth** | JWT dual-token + 3-table RBAC + AES-256-GCM encrypted provider keys |
| 📚 **Knowledge base** | pgvector + HNSW + pg_trgm, hybrid vector & full-text retrieval |
| 🌐 **Embeddable widget** | One `<script>` tag adds chat bubble to any site. Shadow-DOM isolated. 13KB / gzip 4.8KB |
| ⚙️ **DB-driven config** | Providers / Models / Agents editable from admin UI without restart |
| 🐳 **One-click deploy** | `docker compose up -d` spins up 5 services |

---

## 🚀 Quick start (Docker)

```bash
git clone https://github.com/your-org/chameleon.git
cd chameleon

# 1. Set runtime secrets (**REQUIRED on first run**)
cp docker/containers/.env.example docker/containers/.env
vim docker/containers/.env
#   PG_PASSWORD / REDIS_PASSWORD / CHAMELEON_JWT_SECRET / CHAMELEON_CRYPTO_KEY

# 2. Launch
./docker/scripts/run-local.sh

# 3. Open http://localhost:6006
#    Initial admin credentials: docker/containers/data/logs/initial-admin-credentials.txt
```

Full deployment guide: [docs/en/deployment.md](./docs/en/deployment.md) · [中文](./docs/zh/deployment.md)

## 📦 Layout

```
chameleon/
├── backend/                  # FastAPI backend (uv workspace, multi-package)
│   ├── chameleon-core/       # Infra: DB / Redis / JWT / crypto / ORM
│   ├── chameleon-providers/  # Provider abstraction (local / dify / fastgpt)
│   ├── chameleon-agents/     # Business-level local agents
│   ├── chameleon-api/        # Public AI business API
│   ├── chameleon-system/     # Admin management API
│   └── chameleon-app/        # FastAPI launcher
├── frontend/                 # React 19 admin console
│   ├── src/core/             # Shared infra (lib / components / stores / i18n / router)
│   ├── src/system/<module>/  # Business modules (self-contained)
│   └── embed/                # Embeddable widget (separate Vite project)
├── docker/                   # Three-zone (images / containers / scripts)
└── docs/                     # Bilingual docs (zh / en)
```

## 🛠 Stack

**Backend**: Python 3.12 + uv · FastAPI · SQLAlchemy 2.0 async · PostgreSQL 16 + pgvector · Redis · loguru · pytest · ruff

**Frontend**: React 19 · TypeScript strict · Vite · Tailwind v4 + shadcn/ui · TanStack Query · Zustand · react-i18next

**Ops**: Docker + Compose · multi-stage images · BuildKit multi-arch

## 📚 Documentation

| Doc | English | 中文 |
|---|---|---|
| Deployment | [docs/en/deployment.md](./docs/en/deployment.md) | [docs/zh/deployment.md](./docs/zh/deployment.md) |
| Architecture | [docs/en/architecture.md](./docs/en/architecture.md) | [docs/zh/architecture.md](./docs/zh/architecture.md) |
| Admin guide | [docs/en/admin-guide.md](./docs/en/admin-guide.md) | [docs/zh/admin-guide.md](./docs/zh/admin-guide.md) |
| API reference | [docs/en/api-reference.md](./docs/en/api-reference.md) | [docs/zh/api-reference.md](./docs/zh/api-reference.md) |
| ADR | [docs/adr/](./docs/adr/) | same |

## 🤝 Contributing

PRs welcome. Commits follow the Angular convention.

## 📄 License

[MIT](./LICENSE)

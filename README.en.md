# Chameleon

> English · [中文](./README.md)

**Chameleon** is an open-source **all-in-one LLMOps platform** — multi-source agent aggregation + visual workflow orchestration + RAG knowledge base + LangSmith-style trace/eval observability + multi-agent collaboration + embeddable widget & SDK. One repo covering the core capability stack of Dify + LangFuse.

Python 3.12+ · FastAPI · React 19 · PostgreSQL 16 + pgvector · One-click Docker deploy

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

---

## ✨ Capabilities

### Orchestration & agents
- **Multi-source agents** — in-process agents (agentkit SDK) / Dify / FastGPT / OpenAI-compatible vendors, unified behind one HTTP API
- **Visual workflow editor** — ReactFlow node editor: LLM / KB / Tool / HTTP / Code-sandbox / Template / Intent-classifier / Aggregator / Answer / If-Else / Iteration / Parallel / Agent-Debate / Human-in-loop; draft/published versions; chatflow & workflow shapes
- **Workflow-as-agent** — a published graph runs as a `source=graph` agent through the unified invoke endpoint
- **Multi-agent** — A2A protocol + budget gate + recursion-depth limit
- **Code sandbox** — LLM-generated code runs Docker-isolated (network=none / read-only / cap-drop ALL)
- **Plugin marketplace** — remote registry + Ed25519 signature verification + one-click install

### Knowledge base (RAG)
- **Collection types** — generic / FAQ / Wiki / API, each with its own chunker
- **Hybrid retrieval** — vector + BM25 + RRF fusion + metadata filter + reranker
- **VLM image caption** — auto-generates retrievable captions for images (URL refs, no base64 inline)
- **Consistency scan** — orphan chunk / dim mismatch / zero-vector detection + one-click repair
- **Metadata fields** — custom fields + filtered recall
- **Session-file ephemeral RAG** — small files full-text injected / large files chunked & vectorized

### Observability, eval & cost (LangSmith-style)
- **Unified trace tree** — `call_logs` is the single source of truth; nested observations (span + generation); graph nodes emit spans into the same tree; root-row rollup of model / token / cost
- **Session ledger** — `end_user_id` identity layer unifies embed / multi-user sessions
- **Eval operators** — faithfulness / answer_relevance / context_precision / context_recall (local impl, no ragas dep) + dataset A/B
- **OTLP HTTP ingestion** — external app traces land in the Chameleon UI via the SDK

### Integration & DX
- **Embeddable widget** — one `<script>` adds a chat bubble to any site, Shadow-DOM isolated; session resume / file & image input / citation cards / deep appearance customization
- **Python / TypeScript SDK** — `@trace` / `patch_openai` / `patch_all` auto-instrumentation, sync + async
- **agentkit** — write agents in-process: `@agent` + `ctx` gives implicit model / KB / trace access, multiple named model slots, config schema auto-renders a form
- **DB-driven config** — Providers / Models / Agents / KBs editable from the admin UI without restart

---

## 🏗 Layered architecture

The backend is a **uv-workspace multi-package monorepo**, strictly layered following LangChain discipline and enforced by **import-linter** (two contracts, always green):

```
core ← data ← integrations ← engine ← (providers / api / system / app / agents / agentkit)
```

| Layer | Package | Responsibility |
|-------|---------|----------------|
| Protocols | `chameleon-core` | Pure protocols + data structures + observe context. pydantic-only, **no sqlalchemy / langchain** |
| Persistence | `chameleon-data` | ORM models (SQLAlchemy 2.0 async) + infra (db / redis / object store / jwt / crypto / logger) + config |
| Impl | `chameleon-integrations` | Vendor impl: LLM factory / embedding / pgvector / reranker / sandbox / langchain bridges / observe sink / plugins |
| Orchestration | `chameleon-engine` | Graph workflow engine + nodes / retrieval pipeline / eval / a2a / jobs |
| Top | `chameleon-providers` · `-api` · `-system` · `-app` · `-agents` · `-agentkit` | Provider abstraction / public API / admin API / launcher / business agents / agent SDK |

`chameleon-core` is a pydantic-only thin protocol shell; all heavy SDKs (sqlalchemy / langchain / pgvector / docker) sink to upper layers — mirroring `langchain-core`'s "core holds only abstractions".

---

## 🚀 Quick start (Docker)

```bash
git clone https://github.com/garveyhu/Chameleon.git
cd Chameleon

# 1. Set runtime secrets (REQUIRED on first run)
cp docker/containers/.env.example docker/containers/.env
vim docker/containers/.env
#   PG_PASSWORD / REDIS_PASSWORD / CHAMELEON_JWT_SECRET / CHAMELEON_CRYPTO_KEY

# 2. Launch
./docker/scripts/run-local.sh

# 3. Open http://localhost:6006
#    Initial admin credentials: docker/containers/data/logs/initial-admin-credentials.txt
```

Full deployment guide: [docs/en/deployment.md](./docs/en/deployment.md) · [中文](./docs/zh/deployment.md)

---

## 📦 Layout

```
Chameleon/
├── backend/                   # FastAPI backend (uv workspace, import-linter enforced layering)
│   ├── chameleon-core/        # Pure protocols + data structures + observe context (pydantic-only)
│   ├── chameleon-data/        # ORM models + infra (db/redis/object store/jwt/crypto/logger) + config
│   ├── chameleon-integrations/# Vendor impl: LLM/embedding/pgvector/reranker/sandbox/bridges/observe/plugins
│   ├── chameleon-engine/      # Orchestration: graph engine+nodes / retrieval / eval / a2a / jobs
│   ├── chameleon-providers/   # Provider abstraction + local/dify/fastgpt/graph
│   ├── chameleon-agents/      # Business-level local agents
│   ├── chameleon-agentkit/    # In-process agent SDK (@agent + ctx)
│   ├── chameleon-api/         # Public AI API (agent/knowledge/session/task) + OTLP ingestion
│   ├── chameleon-system/      # Admin management API
│   └── chameleon-app/         # FastAPI launcher (assembly + lifespan + DI wiring)
├── frontend/                  # React 19 console (4 domains: Workbench / KB / Observability / Settings)
│   ├── src/core/              # Shared infra (lib / components / stores / router)
│   ├── src/system/<module>/   # Business modules (self-contained)
│   └── embed/                 # Embeddable widget (separate Vite project)
├── sdk/{python,typescript}/   # chameleon-sdk / @chameleon/sdk
├── docker/                    # Three-zone (images / containers / scripts)
└── docs/                      # Bilingual docs + ADR + SDK
```

## 🛠 Stack

**Backend**: Python 3.12 + uv · FastAPI · SQLAlchemy 2.0 async · PostgreSQL 16 + pgvector · Redis · MinIO · loguru · pytest · ruff · **import-linter (layering guard)** · APScheduler · docker-py · PyNaCl

**Frontend**: React 19 · TypeScript strict · Vite · Tailwind v4 + Radix UI · TanStack Query · Zustand · ReactFlow

**SDK**: Python httpx async/sync · TypeScript Node 18+ / browser · OTLP HTTP

**Ops**: Docker + Compose · multi-stage images · BuildKit multi-arch

## 📚 Documentation

| Doc | English | 中文 |
|---|---|---|
| Architecture | [docs/en/architecture.md](./docs/en/architecture.md) | [docs/zh/architecture.md](./docs/zh/architecture.md) |
| Deployment | [docs/en/deployment.md](./docs/en/deployment.md) | [docs/zh/deployment.md](./docs/zh/deployment.md) |
| Admin guide | [docs/en/admin-guide.md](./docs/en/admin-guide.md) | [docs/zh/admin-guide.md](./docs/zh/admin-guide.md) |
| API reference | [docs/en/api-reference.md](./docs/en/api-reference.md) | [docs/zh/api-reference.md](./docs/zh/api-reference.md) |
| ADR | [docs/adr/](./docs/adr/) | same |

## 🤝 Contributing

PRs welcome. Commits follow the Angular convention.

## 📄 License

[MIT](./LICENSE)

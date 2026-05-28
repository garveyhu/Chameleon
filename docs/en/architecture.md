# Architecture

## Overview

```mermaid
graph TB
    classDef edge fill:#4A90D9,stroke:#2E6BA6,stroke-width:2px,color:#fff
    classDef be fill:#48BB78,stroke:#38A169,stroke-width:2px,color:#fff
    classDef store fill:#ED8936,stroke:#C66A32,stroke-width:2px,color:#fff
    classDef provider fill:#9F7AEA,stroke:#7C5CC4,stroke-width:2px,color:#fff

    subgraph Edge["Clients"]
        UI([Admin Console]):::edge
        Widget([Embedded Widget]):::edge
        SDK([External SDK / curl]):::edge
    end

    subgraph App["chameleon-app (FastAPI)"]
        API(chameleon-api business):::be
        SYS(chameleon-system admin):::be
        EMBED(chameleon-api/embed):::be
    end

    subgraph Core["chameleon-core shared"]
        Auth(Auth / RBAC):::be
        Crypto(AES-GCM):::be
    end

    subgraph Providers["chameleon-providers"]
        Local(Local LangGraph):::provider
        Dify(Dify HTTP):::provider
        FastGPT(FastGPT HTTP):::provider
    end

    subgraph DataLayer["Persistence"]
        PG[(PostgreSQL + pgvector)]:::store
        Redis[(Redis)]:::store
    end

    UI ==>|/v1/admin/*| SYS
    Widget ==>|/v1/embed/*| EMBED
    SDK ==>|/v1/invoke| API

    API --> Auth --> PG
    SYS --> Auth
    EMBED --> Redis
    API --> Local
    API --> Dify
    API --> FastGPT
    SYS --> Crypto --> PG
```

## Key decisions

### DB-driven config
JSON files only for first-boot seed; runtime config lives in DB (`providers`, `models`, `agents` tables). Admin UI edits propagate via `reload_agent_registry()` and `reload_llm_cache()`.

### JWT dual-token
- `access_token`: 15 min, in `Authorization: Bearer`
- `refresh_token`: 7 days, in HTTP-only Cookie

axios interceptor catches 401 → auto-refresh → retry once. refresh_token is JS-inaccessible (XSS-safe).

### RBAC three-table
Users ↔ user_roles ↔ roles ↔ role_permissions ↔ permissions, with wildcard support (`*:*`, `users:*`).

### AES-256-GCM provider credentials
Master key in env `CHAMELEON_CRYPTO_KEY` (32 bytes b64). `providers.api_key_encrypted` stores ciphertext; plaintext never logged.

### Snowflake IDs
64-bit: 1 sign + 41 timestamp + 10 instance (`CHAMELEON_INSTANCE_ID`) + 12 seq.

### Provider / Agent Registry
At startup async-loads to in-memory dict. Business hot path reads in O(1). Admin edits trigger `reload_agent_registry()` to refresh.

### Embeddable Widget
Vanilla TS IIFE bundle (13 KB / gzip 4.8 KB). Shadow DOM isolates styles. Origin whitelist + session_token + Redis rate-limit. Messages rendered via `textContent` (XSS-safe).

### Frontend layered (sage style)
```
src/
├── core/                Shared infra (lib / components / stores / i18n / router)
├── system/<module>/     Self-contained business modules
│   ├── pages/           Page components
│   ├── services/        API clients
│   ├── types/           TypeScript types
│   └── routes.ts        Module routes (default-export ModuleRouteConfig)
└── router/index.tsx     import.meta.glob('../system/**/routes.ts')
```

Adding a new business module = creating a new `system/<name>/` directory + a `routes.ts`. No external file edits needed.

## Sequence: one agent call

```mermaid
sequenceDiagram
    participant C as Client
    participant API as chameleon-api
    participant Auth as Auth
    participant Reg as Registry
    participant P as Provider
    participant DB as PG

    C->>+API: POST /v1/agents/qwen-chat/invoke
    API->>+Auth: verify api_key
    Auth->>+DB: SELECT api_keys
    DB-->>-Auth: row
    Auth-->>-API: app_id, scopes

    API->>+Reg: AGENTS["qwen-chat"]
    Reg-->>-API: AgentDef (provider="local")

    API->>+P: PROVIDERS["local"].invoke(ctx)
    P-->>-API: InvokeResult

    API->>+DB: INSERT call_logs
    DB-->>-API: ok
    API-->>-C: Result.ok({answer, session_id})
```

## Capacity expectations

- Backend single instance: ~ 200 RPS (agent-internal latency dominates)
- pgvector HNSW: million-scale chunks retrieval < 50 ms (m=16, ef_search=40)
- Redis: JWT blacklist + session_token + rate limit, ten-thousands QPS on single instance
- Multi-instance: nginx upstream, stateless backend, no session affinity needed

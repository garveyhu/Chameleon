# Admin Guide

How to use the Chameleon admin console.

## First login

1. Find the initial credentials in `backend/logs/initial-admin-credentials.txt`
   (written once on first startup, `chmod 600`).
2. Open http://localhost:6006
3. Log in with the admin credentials; **a password change is forced on first login**
   (the account is seeded with `must_change_password=true`).

## Navigation overview

The console is organized into **four top-level domains**. Each domain exposes a
secondary nav with grouped pages.

```
Workbench  (/agents)
  └ Create
      └ Applications        agents/apps CRUD + enable/disable + test invoke
                            (local / Dify / FastGPT / graph workflows)

Knowledge  (/kbs)
  └ Knowledge
      └ Knowledge bases     KB + collections + documents + chunks

Observability  (/dashboard)
  ├ Overview
  │   └ Dashboard           24h call volume / success rate / tokens, Top agents/apps/models
  ├ Runs
  │   ├ Trace               per-request trace tree (nested observations)
  │   ├ Sessions            ChatSession ledger (multi-turn, end-user identity)
  │   ├ Session files       ephemeral RAG files attached to sessions
  │   └ Playground          interactive invoke sandbox
  ├ Quality & Cost
  │   ├ Cost                cost statistics grouped by model / app / agent
  │   ├ Datasets            eval datasets
  │   └ Eval jobs           evaluation runs
  └ Compliance
      └ Audit logs          admin write-operation trails

Settings  (/providers)
  ├ Access (inbound)
  │   ├ Providers           upstream services (llm / embedding / dify / fastgpt / coze)
  │   ├ Models              models under providers
  │   ├ Plugins             installed plugins
  │   └ Marketplace         plugin marketplace
  ├ Access
  │   ├ Key management      API keys (scope: global / app / kb)
  │   ├ Users               admin users
  │   └ Roles               roles + permission matrix
  └ Platform
      └ Settings            system config + import/export
```

## Typical workflows

### A. Onboard a new LLM provider (e.g., DeepSeek)

1. **Providers** → New
   - kind: `llm`
   - name: `DeepSeek`
   - base_url: `https://api.deepseek.com/v1`
   - api_key: `sk-xxx` (stored AES-256-GCM encrypted; never returned in plaintext)
2. **Providers** list → click **Test** to validate connectivity
3. **Models** → New
   - provider: the `DeepSeek` provider
   - code: `deepseek-chat`
   - kind: `chat`

Saving or editing a provider's credentials triggers an LLM cache reload, so new
keys take effect immediately.

### B. Register a new local agent

Write the Python package under `backend/chameleon-agents/`
(or expose it via the agentkit `@agent` SDK / entry-points), then restart the service
so the registry scan picks it up.

Then **Applications** → New:
- agent_key: matches the registered agent id
- source: `local`
- enabled: ✓

Local agents can only be enabled/disabled and have their default parameters and
model-slot bindings edited from the console — the implementation lives in code.

### C. Onboard an external agent (Dify app)

No code needed:
1. **Providers** → create or confirm a `dify` provider (base_url + api_key)
2. **Applications** → New
   - agent_key: e.g. `customer-bot`
   - source: `dify`
   - config: provider-specific (e.g. `{"app_id": "dify-app-xxx", ...}`)

The same flow applies to `fastgpt` and `coze` providers.

### D. Publish a graph workflow as an agent

1. Build and **publish** a workflow in the graph editor (Workbench).
2. **Applications** → New
   - source: `graph`
   - linked to the published graph; the runtime serves its `published_spec`.

### E. Create an API key

API keys are scoped, not owned by an "app" container.

1. **Key management** → New key
   - scope_type: `global` (calls every service), `app` (one agent/app),
     or `kb` (one knowledge base)
   - scope_ref: the in-domain target (agent_key for `app`, kb_key for `kb`;
     leave empty for `global`)
2. The plaintext token is shown on creation. Prefixes encode the scope:
   `chm_` (global), `app-` (app), `kbs-` (kb). The plaintext is retained server-side
   so it can be copied again later from the key detail.
3. Business call (app-scoped key implies the agent; global key passes `agent_key` in the body):
   ```
   POST /v1/invoke
   Authorization: Bearer <token>
   Content-Type: application/json

   {"input": {"messages": [{"role": "user", "content": "hi"}]}}
   ```
   OpenAI-compatible endpoints are also exposed under `/v1` for drop-in clients.

### F. Generate an embeddable widget

1. **Applications** → open an app → embed configuration, or create an embed config
   that links an agent + API key.
   - allowed_origins: restrict which sites may load the widget
   - ui_config / behavior / session_policy: customize appearance and session handling
2. Copy the generated JS widget or iframe snippet (keyed by `embed_key`) into the
   business website.

## Users & permissions

Permission code format: `<resource>:<action>` (e.g. `users:read`, `*:*`, `agents:*`).
A `resource:*` grant covers every action on that resource; `*:*` grants everything.

Built-in roles:
- **admin** — `*:*` (every permission; auto-synced as new permission points are added)
- **developer** — full CRUD on business resources (providers, models, agents, kbs,
  api_keys, graphs, tools, datasets, embed_configs, ...) plus dashboard / call_logs /
  playground; **cannot** manage users, roles, permissions, or settings
- **viewer** — read-only across all resources plus dashboard

## Knowledge bases

1. **Knowledge bases** → New KB (pick an embedding model)
2. Create a collection. The `collection_type` (`generic` / `faq` / `wiki` / `api`)
   selects the chunker and is **immutable once set**:
   - `generic` — char/token/paragraph chunking for general docs
   - `faq` — parses `Q: ... / A: ...` pairs, one chunk per pair
   - `wiki` — long-form text split by headings, preserving the heading path
   - `api` — OpenAPI YAML/JSON, one chunk per endpoint
3. Upload documents (PDF / Markdown / TXT). Chunking + embedding run as background
   tasks; track progress in the **Tasks** module (`/v1/tasks`).
4. Retrieval is hybrid: vector + BM25 + RRF fusion + metadata filtering + reranker.
   Link a KB to an agent and top-k results are injected at invoke time.

## Audit & monitoring

### Trace / call logs

`call_logs` is the single source of truth for traces. Each request writes a row,
and nested observations (LLM generations, KB retrievals, tool calls, graph node spans)
are linked via `parent_id` into a trace tree (root row has `parent_id = NULL`).

Notable columns: `request_id`, `app_id` (caller/source label), `agent_key`,
`model_code`, `channel` (api / openai / embed / playground / internal), `success`,
`code`, `duration_ms`, `prompt_tokens` / `completion_tokens` / `total_tokens`,
`cost_usd`, `request_payload`, `response_payload`. The root row rolls up
model / token / cost from its children.

In the console, **Trace** and **Sessions** are separate tabs: Trace is per-request,
Sessions groups requests into multi-turn `ChatSession`s by `end_user_id`.

### Audit logs

All admin write operations are logged (who, when, what, IP/UA).

## Config import / export

**Settings** page → import / export (admin role only — export contains secrets):

- **Export** downloads a zip:
  - `model.json` — providers + models (provider api_key decrypted into plaintext,
    decoupled from this host's master key)
  - `agents.yaml` — external agents (`source != 'local'`)
  - `users.json` — users + roles + role_permissions (includes `password_hash`)
  - `api_keys.json` — api keys (`key_hash` cannot be reversed to plaintext)
- **Import** uploads a zip to overwrite (DANGEROUS — recovery / migration only).

## Security tips

- [ ] Rotate provider api_keys regularly (editing re-encrypts and invalidates the old
      ciphertext immediately; the LLM cache reloads on save)
- [ ] Rotate API keys regularly; revoke unused keys
- [ ] Restrict embed `allowed_origins` to known business domains
- [ ] Monitor the `call_logs.success = false` ratio
- [ ] Review high-risk operations in `audit_logs`
- [ ] Keep `backend/logs/initial-admin-credentials.txt` out of version control and
      delete it after the first password change

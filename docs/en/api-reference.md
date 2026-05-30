# API Reference

Full OpenAPI: http://localhost:7009/docs (interactive) or `/openapi.json` (raw).

This document lists high-frequency endpoints and contract conventions. The
backend runs as a thin FastAPI launcher (`chameleon-app`) that mounts routers
from `chameleon-api` (public AI service API) and `chameleon-system` (internal
admin API). Default port is `7009`.

## Conventions

### Unified response envelope

```json
{ "code": 200, "message": "ok", "data": {}, "success": true }
```

Business exceptions set `success: false`; `code` is a 5-digit business error
code (not the HTTP status). HTTP status is derived from the business code
(`code_to_http_status`): `200 → 200`, `4xxxx → 4xx` same bucket
(`40001 → 400`, `40110 → 401`, `40310 → 403`, `40400 → 404`, `42901 → 429`),
`5xxxx → 500`, `6xxxx → 502` (provider errors; `ProviderUnreachable → 504`).

### Error codes (selected)

| code | HTTP | Meaning |
|---|---|---|
| 200 | 200 | OK |
| 40001 | 400 | Validation error |
| 40101 | 401 | API key missing |
| 40102 | 401 | API key invalid |
| 40103 | 401 | API key revoked |
| 40110 | 401 | JWT missing |
| 40111 | 401 | JWT expired |
| 40112 | 401 | JWT invalid |
| 40113 | 401 | Refresh token invalid |
| 40301 | 403 | Admin scope required |
| 40302 | 403 | Agent not in key scope |
| 40303 | 403 | KB not in key scope |
| 40310 | 403 | Permission denied |
| 40400 | 404 | Not found |
| 40402 | 404 | Session not found |
| 42901 | 429 | App rate limited |
| 50001 | 500 | Internal error |
| 60020 | 504 | Provider unreachable |

### Auth

| Endpoint type | Auth method |
|---|---|
| `/v1/admin/*` | `Authorization: Bearer <jwt-access-token>` (+ permission checks) |
| `/v1/invoke`, `/v1/chat/completions`, `/v1/kb/*`, `/v1/sessions/*`, `/v1/files/*`, `/v1/tasks/*`, `/v1/otel/*` | `Authorization: Bearer <api-key>` |
| `/v1/embed/{embed_key}/*` | None (public; checks Origin + session_token) |
| `/v1/auth/refresh` | HTTP-only Cookie `chameleon_refresh` |

API keys are scoped. `scope_type` is one of `global` / `app` / `kb`, encoded in
the key prefix: `global → chm_`, `app → app-`, `kb → kbs-`. An `app`-scoped key
is implicitly bound to one agent; a `global` key must name the target explicitly
(`agent_key` in the invoke body, `kb_key` query param for KB endpoints). A
`kb`-scoped key may only call `/v1/kb/*`.

## I. Auth

### POST /v1/auth/login

```json
// Request
{ "username": "admin", "password": "..." }

// Response — refresh_token written to HTTP-only Cookie (chameleon_refresh)
{ "code": 200, "data": { "access_token": "...", "token_type": "bearer", "user": {...} } }
```

### POST /v1/auth/refresh
No body. Reads the `chameleon_refresh` Cookie. Returns a new access_token and
rotates the refresh_token Cookie (old refresh `jti` is blacklisted).

### POST /v1/auth/logout
Blacklists the current access token; clears the refresh_token Cookie.

### GET /v1/auth/me
Returns the current user (roles + permission points).

### POST /v1/auth/change-password
`{ "old_password": "...", "new_password": "..." }`

### POST /v1/auth/first-change-password
First-login password change (no old password needed; used when
`must_change_password` is set). `{ "new_password": "..." }`

## II. Agent invoke

Key-bound application identity (Dify style): the API key carries the app
identity. An `app`-scoped key resolves the target agent from its binding; a
`global` key passes `agent_key` in the body.

### POST /v1/invoke

```http
POST /v1/invoke
Authorization: Bearer <api-key>
Content-Type: application/json
```

```json
{
  "input": "hello",
  "session_id": "optional — omit to start a new session",
  "user": "optional external end-user id",
  "stream": false,
  "agent_key": "required only for global-scoped keys"
}
```

`input` may be a string (server takes session history) or a list of messages
(client manages history). `attachments`, `context`, and `options` are optional.

Non-stream response:
```json
{ "code": 200, "data": { "answer": "...", "session_id": "...", "request_id": "..." } }
```

Stream response (`stream: true`): `text/event-stream` SSE.

### GET /v1/info
Returns the application bound to the current key (scope_type + agent info).

### POST /v1/chat/completions (OpenAI-compatible)
Drop-in OpenAI chat-completions gateway: `model` = `agent_key`. Same auth as
`/v1/invoke`. `stream: true` emits `chat.completion.chunk` SSE + `[DONE]`. Lets
any OpenAI client/SDK call platform agents (including graph-orchestrated ones)
by swapping `base_url`.

## III. Knowledge Base API (key-scoped)

Prefix `/v1/kb`. A `kb`-scoped key is bound to one KB; a `global` key passes
`?kb_key=...`.

```
GET    /v1/kb                          # KB metadata
POST   /v1/kb/update
POST   /v1/kb/delete

POST   /v1/kb/documents                # ingest (async indexing task)
GET    /v1/kb/documents                # paged list
GET    /v1/kb/documents/{doc_id}
POST   /v1/kb/documents/{doc_id}/update
POST   /v1/kb/documents/{doc_id}/delete

POST   /v1/kb/search                   # hybrid retrieval (vector + BM25 + RRF + reranker)
```

## IV. Sessions API (key-scoped)

Prefix `/v1/sessions`. Sessions (`ChatSession` + `end_user_id` identity layer)
back embedded and multi-user chat.

```
GET    /v1/sessions                              # paged list
GET    /v1/sessions/{session_id}
GET    /v1/sessions/{session_id}/messages        # paged
POST   /v1/sessions/{session_id}/delete
```

## V. Files & Tasks

```
POST   /v1/files/presigned-upload          # presigned object-store upload
POST   /v1/files/{object_id}/finalize      # finalize uploaded object

GET    /v1/tasks/{task_id}                 # async task status (e.g. ingestion)
```

## VI. OTLP ingestion

OpenTelemetry traces ingestion (auth via API key; anonymous reporting rejected;
≤ 5000 spans per batch).

```
POST   /v1/otel/v1/traces                  # OTLP HTTP/JSON
```

## VII. Embed Widget API (public)

Prefix `/v1/embed/{embed_key}`. No API key; auth is `Origin` allowlist +
`session_token`.

### GET /v1/embed/{embed_key}/config
Returns public UI config + behavior. Server validates the `Origin` header
against `allowed_origins`.

### POST /v1/embed/{embed_key}/session
Issues a `session_token`. Body optionally carries `device_id` /
`external_user_id` / `jwt_token` per the embed's `identification_mode`.
Returns `{ "session_token": "...", "expires_in": 3600 }`.

### POST /v1/embed/{embed_key}/invoke
`{ "session_token": "...", "input": "..." }` → `{ "answer": "...", "session_id": "..." }`

### POST /v1/embed/{embed_key}/invoke/stream
SSE streaming variant.

### Session management & files (end-user scoped, by session_token)
```
GET    /v1/embed/{embed_key}/sessions
GET    /v1/embed/{embed_key}/sessions/{session_id}/messages
POST   /v1/embed/{embed_key}/sessions/new
POST   /v1/embed/{embed_key}/sessions/{session_id}/delete
POST   /v1/embed/{embed_key}/sessions/{session_id}/name

POST   /v1/embed/{embed_key}/files/presigned-upload
POST   /v1/embed/{embed_key}/files/{object_id}/finalize
POST   /v1/embed/{embed_key}/files/{file_id}/status
GET    /v1/embed/{embed_key}/sessions/{session_id}/files
POST   /v1/embed/{embed_key}/sessions/{session_id}/files/{file_id}/delete

POST   /v1/embed/{embed_key}/suggest-followups
POST   /v1/embed/{embed_key}/feedback
```

## VIII. Admin API (excerpt)

Prefix `/v1/admin/*`, JWT auth + permission checks.

### Users
```
GET    /v1/admin/users
POST   /v1/admin/users
POST   /v1/admin/users/{id}/update
POST   /v1/admin/users/{id}/delete
POST   /v1/admin/users/{id}/reset-password
```

### Roles / Permissions
```
GET    /v1/admin/roles
POST   /v1/admin/roles
POST   /v1/admin/roles/{id}/update
POST   /v1/admin/roles/{id}/delete
POST   /v1/admin/roles/{id}/permissions
GET    /v1/admin/permissions
```

### Providers / Models / Agents
```
GET    /v1/admin/providers
POST   /v1/admin/providers
POST   /v1/admin/providers/{id}/update
POST   /v1/admin/providers/{id}/test

GET    /v1/admin/models
POST   /v1/admin/models

GET    /v1/admin/agents
POST   /v1/admin/agents
POST   /v1/admin/agents/{id}/update
POST   /v1/admin/agents/{id}/delete
POST   /v1/admin/agents/{id}/test
GET    /v1/admin/agents/{id}/api-keys      # agent-scoped keys
POST   /v1/admin/agents/{id}/api-keys      # returns plaintext token (once)
```

### API Keys
Scope = `global` / `app` / `kb`; prefix `chm_` / `app-` / `kbs-`.
```
GET    /v1/admin/api-keys
POST   /v1/admin/api-keys                  # returns plaintext token (once)
POST   /v1/admin/api-keys/{key_id}/revoke
```

### Knowledge bases / Graphs
```
GET    /v1/admin/kbs
POST   /v1/admin/kbs
GET    /v1/admin/graphs
POST   /v1/admin/graphs
```

### Embed configs
```
GET    /v1/admin/embed-configs
POST   /v1/admin/embed-configs
POST   /v1/admin/embed-configs/{config_id}/update
POST   /v1/admin/embed-configs/{config_id}/delete
```

### Observability
`call_logs` is the single source of truth for traces. A trace is a tree of
nested observations (span + generation); graph nodes emit spans into the trace
tree; the root row is rolled up with model / token / cost. The UI splits this
into a **Trace** tab (per-run) and a **Session** tab (per-thread).
```
GET    /v1/admin/call-logs                 # paged traces (root rows)
GET    /v1/admin/call-logs/{call_log_id}
GET    /v1/admin/call-logs/{request_id}/tree   # nested observation tree
GET    /v1/admin/sessions                  # session (thread) list
GET    /v1/admin/audit-logs
GET    /v1/admin/dashboard/overview
```

### Eval / Datasets / Scores
```
GET    /v1/admin/eval-jobs
GET    /v1/admin/eval-templates
GET    /v1/admin/datasets
GET    /v1/admin/scores
```

### Other admin domains
`app-templates` · `plugins` · `marketplace` · `tools` · `schemas` · `search` ·
`playground` · `session-files` · `settings`.

### Settings
```
POST   /v1/admin/settings/export    # download zip
POST   /v1/admin/settings/import    # upload zip (multipart)
```

## IX. SDK

- **Python**: `chameleon-sdk` — `httpx` sync + async clients; `@trace`,
  `patch_openai`, `patch_all` for auto-instrumentation.
- **TypeScript**: `@chameleon/sdk`.
- **OTLP HTTP** for trace export (see `/v1/otel/v1/traces`).
- OpenAI-compatible protocol layer (`POST /v1/chat/completions`), so
  `openai-python` and other OpenAI clients work by swapping `base_url`.

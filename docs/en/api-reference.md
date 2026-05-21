# API Reference

Full OpenAPI: http://localhost:7009/docs (interactive) or `/openapi.json` (raw).

This document lists high-frequency endpoints and contract conventions.

## Conventions

### Unified response envelope

```json
{ "code": 0, "message": "ok", "data": {}, "success": true }
```

Business exceptions set `success: false`; `code` is a business error code (not HTTP status). HTTP status is mapped from the business code.

### Error codes (selected)

| code | HTTP | Meaning |
|---|---|---|
| 0 | 200 | OK |
| 4001 | 401 | JWT missing/expired |
| 4002 | 401 | JWT blacklisted |
| 4030 | 403 | Forbidden |
| 4040 | 404 | Not found |
| 4220 | 422 | Validation error |
| 4290 | 429 | Rate limited |
| 5000 | 500 | Server error |

### Auth

| Endpoint type | Auth method |
|---|---|
| `/v1/admin/*` | `Authorization: Bearer <jwt-access-token>` |
| `/v1/agents/{key}/invoke` | `Authorization: Bearer <app-api-key>` |
| `/v1/embed/{embed_key}/*` | None (public; checks Origin + session_token) |
| `/v1/auth/refresh` | HTTP-only Cookie `refresh_token` |

## I. Auth

### POST /v1/auth/login

```json
// Request
{ "username": "admin", "password": "..." }

// Response — refresh_token written to HTTP-only Cookie
{ "code": 0, "data": { "access_token": "...", "token_type": "bearer", "user": {...} } }
```

### POST /v1/auth/refresh
No body. Reads Cookie. Returns new access_token + rotates refresh_token Cookie.

### POST /v1/auth/logout
Blacklists current access; clears refresh_token Cookie.

### POST /v1/auth/change-password
`{ "old_password": "...", "new_password": "..." }`

## II. Agent invoke

### POST /v1/agents/{agent_key}/invoke

```http
POST /v1/agents/qwen-chat/invoke
Authorization: Bearer <app-api-key>
Content-Type: application/json
```

```json
{ "input": "hello", "session_id": "optional", "stream": false }
```

Non-stream response:
```json
{ "code": 0, "data": { "answer": "...", "session_id": "...", "request_id": "..." } }
```

Stream response (`stream: true`): `text/event-stream` SSE.

## III. Embed Widget API (public)

### GET /v1/embed/{embed_key}/config
Server validates `Origin` header against `allowed_origins`.

### POST /v1/embed/{embed_key}/session
Returns `{ "session_token": "...", "expires_in": 3600 }`.

### POST /v1/embed/{embed_key}/invoke
`{ "session_token": "...", "input": "..." }` → `{ "answer": "...", "session_id": "..." }`

## IV. Admin API (excerpt)

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
POST   /v1/admin/agents/{id}/update
POST   /v1/admin/agents/{id}/invoke-test
```

### Apps / API Keys
```
GET    /v1/admin/apps
POST   /v1/admin/apps
GET    /v1/admin/apps/{id}/api-keys
POST   /v1/admin/apps/{id}/api-keys       # returns plaintext token (once)
POST   /v1/admin/api-keys/{id}/delete
```

### Embed configs
```
GET    /v1/admin/embed-configs
POST   /v1/admin/embed-configs
POST   /v1/admin/embed-configs/{id}/update
POST   /v1/admin/embed-configs/{id}/delete
```

### Logs / Dashboard
```
GET    /v1/admin/call-logs
GET    /v1/admin/audit-logs
GET    /v1/admin/dashboard/overview
```

### Settings
```
POST   /v1/admin/settings/export    # download zip
POST   /v1/admin/settings/import    # upload zip (multipart)
```

## V. SDK

No official SDK in v0.1. HTTP contract is stable.

Roadmap:
- Python: `pip install chameleon-sdk`
- Node.js: `npm install @chameleon/sdk`
- OpenAI-compatible protocol layer (so `openai-python` works by swapping base_url)

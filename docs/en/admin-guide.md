# Admin Guide

How to use the Chameleon admin console.

## First login

1. Find credentials in `docker/containers/data/logs/initial-admin-credentials.txt`
2. Open http://localhost:6006
3. Login with admin credentials; **password change is forced on first login**

## Menu overview

```
Overview
  └ Dashboard          24h call volume + Top agents/apps

AI Capabilities
  ├ Agents             CRUD + enable/disable + test invoke
  ├ Providers          upstream services (Dify / FastGPT / OpenAI-compat)
  ├ Models             models under providers
  ├ Knowledge bases    KB + Doc + Chunk
  └ Embedded Agents    generate embeddable chat widget

Access / Calls
  ├ Apps & API Keys    business client identity + credentials
  ├ Call logs          per-invoke records (query/filter)
  ├ Users              admin users
  └ Roles              roles + permission matrix

System
  ├ Audit logs         admin write-operation trails
  ├ Settings           import/export seed JSON
  └ About              version / license
```

## Typical workflows

### A. Onboard a new LLM provider (e.g., DeepSeek)

1. **Providers** → New
   - code: `deepseek`
   - kind: `openai_compatible`
   - base_url: `https://api.deepseek.com/v1`
   - api_key: `sk-xxx` (auto AES-256-GCM encrypted)
2. **Providers** list → click **Test** button
3. **Models** → New
   - provider: `deepseek`
   - code: `deepseek-chat`
   - kind: `chat`

### B. Register a new local agent

Write the Python package under `backend/chameleon-agents/<key>/`, restart service.

Then **Agents** → New:
- agent_key: matches `get_metadata().id`
- source: `local`
- enabled: ✓

### C. Onboard external agent (Dify app)

No code needed:
1. **Providers** → confirm `dify` provider's base_url
2. **Agents** → New
   - agent_key: e.g. `customer-bot`
   - source: `dify`
   - config: `{"app_id": "dify-app-xxx", "api_key": "dify-api-key-xxx"}`

### D. Create app + API key

1. **Apps & API Keys** → New app
2. New API key under app → **plaintext token shown ONCE — save immediately**
3. Business call:
   ```
   POST /v1/agents/customer-bot/invoke
   Authorization: Bearer <token>
   ```

### E. Generate embeddable widget

1. **Embedded Agents** → New
   - relate agent + app
   - allowed_origins: one URL per line
2. List → **Embed Code** button
3. Copy JS Widget or iframe snippet to the business website

## Users & Permissions

Permission code format: `<resource>:<action>` (e.g. `users:read`, `*:*`, `agents:*`).

Built-in roles:
- **admin** — `*:*`
- **viewer** — read-only
- **developer** — agents / kbs / providers / models full + read others

## Knowledge bases

1. **Knowledge bases** → New KB (pick embedding model)
2. KB detail → upload docs (PDF / Markdown / TXT)
3. Backend async chunks + embeds; see **Tasks** module
4. Link to agent; on invoke, top-k retrieval auto-injects into system prompt

## Audit & Monitoring

### Call logs
Each `/v1/agents/*/invoke` writes a `call_logs` row (request_id / app_id / agent_key / success / latency / tokens / request body / response body).

### Audit logs
All admin write ops are logged (who, when, what, IP/UA).

## Config import/export

**Settings** page:
- **Export**: download current providers / models / agents / roles / permissions as zip
- **Import**: upload zip to overwrite (DANGEROUS, recovery / migration only)

## Security tips

- [ ] Enable 2FA for admin (roadmap, not in v0.1)
- [ ] Rotate provider api_keys regularly (UI edits → old ciphertext invalidated immediately)
- [ ] Rotate app api_keys regularly
- [ ] Monitor `call_logs.success=false` ratio
- [ ] Monitor high-risk operations in `audit_logs`

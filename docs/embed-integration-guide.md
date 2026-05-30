# 嵌入式应用接入指南

> 嵌入式接入契约。覆盖：终端用户身份识别（三模式）、会话颁发、会话管理（列表/续接/删除/改名）、错误处理。

## 1. 基本流程

```
1. 业务方网页拉配置 ────────→ GET  /v1/embed/{embed_key}/config
2. 颁 session_token（带身份）→ POST /v1/embed/{embed_key}/session
3. 对话（非流 / 流式）        → POST /v1/embed/{embed_key}/invoke[/stream]
4. 会话管理（可选）           → GET/POST /v1/embed/{embed_key}/sessions[/...]
```

所有请求需带 `Origin` 头，匹配 embed_config 的 `allowed_origins` 白名单（`["*"]` = 公开）。

## 2. 终端用户身份识别（三种模式）

`session_policy.identification_mode` 在后台「嵌入应用」配置项里选其一：

### 2.1 anonymous_device（默认）

前端 widget 在 `localStorage` 持久化一个 UUID 作为 `device_id`，颁 token 时带上：

```bash
POST /v1/embed/{embed_key}/session
{
  "device_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

后端 `"anon_" + sha256(device_id)[:24]` → `end_user_id`。同设备同浏览器 = 同 end_user，浏览器清缓存后变新人。

### 2.2 external_user_id（接入方维护）

业务方在自家系统里已经有用户 id（如 SaaS 客户编号），颁 token 时直接传：

```bash
POST /v1/embed/{embed_key}/session
{
  "external_user_id": "biz-user-12345"
}
```

后端原样存进 `end_user_id`。**注意**：值直接信任接入方，要防止被前端篡改，建议改用 signed_jwt 模式。

### 2.3 signed_jwt（推荐生产用）

接入方后端用 HS256 签一个 JWT（密钥在「嵌入应用」配置里录入并加密落库），前端传给颁 token 端点：

```bash
POST /v1/embed/{embed_key}/session
{
  "jwt_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

JWT payload 必带 `sub` claim 当 `end_user_id`，可选 `exp` 标签到期时间。后端用 `session_policy.jwt_signing_secret_encrypted` 解出密钥验签。

## 3. 会话管理端点

颁完 token 后，前端可调以下端点维护历史会话——**全部按 token 上绑定的 end_user_id 隔离**，跨用户访问会 404。

| 端点 | 用途 |
|---|---|
| `GET /v1/embed/{embed_key}/sessions?session_token=XXX` | 列当前 end_user 的历史会话（按活跃倒序） |
| `GET /v1/embed/{embed_key}/sessions/{session_id}/messages?session_token=XXX` | 切到某历史会话，加载消息 |
| `POST /v1/embed/{embed_key}/sessions/new` | 显式开新对话（不靠刷新；body: `{session_token}`） |
| `POST /v1/embed/{embed_key}/sessions/{session_id}/delete` | 软删（受 `allow_user_manage` 限制） |
| `POST /v1/embed/{embed_key}/sessions/{session_id}/name` | 重命名（同上） |

`session_policy.allow_user_manage=false` 时删除/改名端点返 403。

## 4. `session_policy` 配置项

| 字段 | 说明 | 默认 |
|---|---|---|
| `identification_mode` | `anonymous_device` / `external_user_id` / `signed_jwt` | `anonymous_device` |
| `jwt_signing_secret_encrypted` | signed_jwt 模式的 HS256 共享密钥（密文落库） | `null` |
| `show_history_sidebar` | widget 是否显示历史侧栏 | `true` |
| `auto_resume_last` | widget 加载时是否自动续接上次会话 | `true` |
| `allow_user_manage` | 是否允许用户删除/改名自己的会话 | `true` |
| `max_history_days` | 历史会话列表的时间窗（天） | `90` |

## 5. 调用流量归属

embed 调用产生的 `call_logs` 行带的字段：

| 字段 | 取值 |
|---|---|
| `channel` | `'embed'`（恒定） |
| `app_id` | `'embed:{embed_key}'`（自由标签） |
| `api_key_id` | embed_config.api_key_id（绑了 owner key 就有，否则 NULL） |
| `end_user_id` | token 上绑的终端用户 id |
| `session_id` | 当前会话 |
| `agent_key` | 该 embed 关联的 agent |

generation 子行（每次 LLM 调用一条，`observation_type='generation'`）自动由 BaseLLM 回调写入，归属字段与父 trace 一致。

按用户计费/限流：`SELECT SUM(cost_usd), SUM(total_tokens) FROM call_logs WHERE channel='embed' AND end_user_id=? AND created_at > ?`。

## 6. 错误码常见

- `40402 SessionNotFound`：session_id 不存在 / 越权（不属于 token 上绑的 end_user）
- `40112 JwtInvalid`：jwt_token 验签失败、过期、缺 sub，或 session_token 不匹配 embed_key
- `42901 AppRateLimit`：单 token 频率超限（默认 5 msg/min）
- `40310 PermissionDenied`：origin 不在白名单 / allow_user_manage=false 时的删/改名

## 7. 历史会话不串号原则

- 终端用户隔离：所有列表/查询都按 token 上绑的 `end_user_id` 过滤
- session_id 一致性：同一 session_id 不允许跨 agent / 跨 end_user 续接（后端校验）
- 未绑 end_user 的老 token：`GET /sessions` 返空，避免裸 token 看到混合数据

---

**相关后端文件**

- `chameleon-api/src/chameleon/api/embed/schemas.py` — SessionPolicy / CreateSessionRequest DTO
- `chameleon-api/src/chameleon/api/embed/service.py` — `resolve_end_user_from_request` + 三模式分流
- `chameleon-api/src/chameleon/api/embed/session.py` — Redis token + end_user_id 绑定
- `chameleon-api/src/chameleon/api/embed/api.py` — 端点路由
- `chameleon-data/src/chameleon/data/models/embed_config.py` — `api_key_id` + `session_policy` 列
- `chameleon-data/src/chameleon/data/models/api_key.py` — `CallLog` ORM（call_logs 归属字段）
- `chameleon-integrations/src/chameleon/integrations/observe/llm_recorder.py` — generation 自动落账

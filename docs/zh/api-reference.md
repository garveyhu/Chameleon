# API 参考

完整 OpenAPI 文档：启动服务后访问 http://localhost:7009/docs（交互式）或 `/openapi.json`（原始）。

本文档只列高频接口和契约约定。

## 通用约定

### 统一响应

所有接口返回 JSON 包装：

```json
{
  "code": 0,
  "message": "ok",
  "data": { /* 业务数据 */ },
  "success": true
}
```

业务异常 `success: false`，`code` 是业务错误码（非 HTTP status）。HTTP 状态码由错误码映射。

### 错误码（节选）

| code | HTTP | 含义 |
|---|---|---|
| 0 | 200 | 成功 |
| 4001 | 401 | JWT 缺失 / 过期 |
| 4002 | 401 | JWT 黑名单 / 已注销 |
| 4030 | 403 | 权限不足 |
| 4040 | 404 | 资源不存在 |
| 4220 | 422 | 参数校验失败 |
| 4290 | 429 | 限流 |
| 5000 | 500 | 服务异常 |

### 鉴权

| Endpoint 类型 | 鉴权方式 |
|---|---|
| `/v1/admin/*` | `Authorization: Bearer <jwt-access-token>` |
| `/v1/invoke` | `Authorization: Bearer <app-api-key>` |
| `/v1/embed/{embed_key}/*` | 无（公开，校验 Origin + session_token） |
| `/v1/auth/refresh` | HTTP-only Cookie `refresh_token` |

## 一、Auth

### POST /v1/auth/login

```json
// Request
{ "username": "admin", "password": "..." }

// Response
{
  "code": 0,
  "data": {
    "access_token": "eyJ...",  // 15min
    "token_type": "bearer",
    "user": { "id": 1, "username": "admin", "must_change_password": false, ... }
  }
}
// refresh_token 写入 HTTP-only Cookie
```

### POST /v1/auth/refresh

无需 body，依赖 Cookie。返回新的 access_token + 新的 refresh_token Cookie。

### POST /v1/auth/logout

把当前 access 加入黑名单，清 refresh_token Cookie。

### POST /v1/auth/change-password

```json
{ "old_password": "...", "new_password": "..." }
```

## 二、Agent invoke（业务方调用）

### POST /v1/agents/{agent_key}/invoke

```http
POST /v1/agents/qwen-chat/invoke
Authorization: Bearer <app-api-key>
Content-Type: application/json
```

```json
{
  "input": "你好",
  "session_id": "optional-session-id",
  "stream": false
}
```

非流式响应：

```json
{
  "code": 0,
  "data": {
    "answer": "你好！有什么可以帮你的？",
    "session_id": "abc123",
    "request_id": "req-xxx"
  }
}
```

流式响应（`stream: true`）：返回 `text/event-stream` SSE：

```
data: {"delta":"你好","done":false}
data: {"delta":"！","done":false}
data: {"delta":"","done":true,"session_id":"abc123"}
```

## 三、嵌入式 Widget API（公开）

### GET /v1/embed/{embed_key}/config

服务端校验请求头 `Origin` 是否在 `allowed_origins` 白名单。

```json
{
  "code": 0,
  "data": {
    "embed_key": "abc123",
    "name": "官网客服",
    "ui_config": { "title": "...", "primary_color": "#0ea5e9" },
    "behavior": { "welcome_message": "...", "placeholder": "..." }
  }
}
```

### POST /v1/embed/{embed_key}/session

颁 session_token（Redis TTL 1h），后续 `invoke` 用：

```json
{ "session_token": "...", "expires_in": 3600 }
```

### POST /v1/embed/{embed_key}/invoke

```json
{ "session_token": "...", "input": "你好" }
```

```json
{ "code": 0, "data": { "answer": "...", "session_id": "..." } }
```

## 四、Admin API（节选）

完整列表见 `/openapi.json`，路径前缀 `/v1/admin/*`，统一 JWT 鉴权 + 权限点校验。

### 用户管理

```
GET    /v1/admin/users                # 列表
POST   /v1/admin/users                # 创建
POST   /v1/admin/users/{id}/update    # 更新
POST   /v1/admin/users/{id}/delete    # 删除（软删）
POST   /v1/admin/users/{id}/reset-password
```

### 角色 / 权限

```
GET    /v1/admin/roles
POST   /v1/admin/roles
POST   /v1/admin/roles/{id}/update
POST   /v1/admin/roles/{id}/delete
POST   /v1/admin/roles/{id}/permissions    # 同步权限
GET    /v1/admin/permissions               # 所有权限点
```

### Provider / Model / Agent

```
GET    /v1/admin/providers
POST   /v1/admin/providers
POST   /v1/admin/providers/{id}/update     # 含 api_key 重加密
POST   /v1/admin/providers/{id}/test       # 连通性测试

GET    /v1/admin/models
POST   /v1/admin/models
...

GET    /v1/admin/agents
POST   /v1/admin/agents/{id}/update        # 改 enabled / config
POST   /v1/admin/agents/{id}/invoke-test   # admin 测试调用
```

### 应用 / API Key

```
GET    /v1/admin/apps
POST   /v1/admin/apps
GET    /v1/admin/apps/{id}/api-keys
POST   /v1/admin/apps/{id}/api-keys        # 返回明文 token（仅一次）
POST   /v1/admin/api-keys/{id}/delete
```

### 嵌入式配置

```
GET    /v1/admin/embed-configs
POST   /v1/admin/embed-configs
POST   /v1/admin/embed-configs/{id}/update
POST   /v1/admin/embed-configs/{id}/delete
```

### 调用日志 / 审计日志 / Dashboard

```
GET    /v1/admin/call-logs              # 分页 + 多维过滤
GET    /v1/admin/audit-logs             # 分页
GET    /v1/admin/dashboard/overview     # 4 个数字 + 24h 曲线 + top-N
```

### 配置导入导出

```
POST   /v1/admin/settings/export        # 下载 zip
POST   /v1/admin/settings/import        # 上传 zip（multipart/form-data）
```

## 五、SDK

v0.1 暂未发布官方 SDK。直接 HTTP 调用即可，对外契约稳定。

未来计划：
- Python: `pip install chameleon-sdk`
- Node.js: `npm install @chameleon/sdk`
- 兼容 OpenAI SDK 的协议层（让 `openai-python` 直接换 base_url 就能用）

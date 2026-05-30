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

> 例外：OpenAI 兼容端点（`/v1/chat/completions`）和 OTLP 摄入端点（`/v1/otel/v1/traces`）按各自协议返回原生结构，不套统一响应包装。

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
| `/v1/admin/*` | `Authorization: Bearer <jwt-access-token>` + 权限点校验 |
| `/v1/invoke` · `/v1/info` · `/v1/chat/completions` | `Authorization: Bearer <api-key>`（key 即身份） |
| `/v1/sessions/*` · `/v1/kb/*` · `/v1/files/*` · `/v1/tasks/*` | `Authorization: Bearer <api-key>` |
| `/v1/embed/{embed_key}/*` | 无 JWT（公开，校验 Origin 白名单 + session_token） |
| `/v1/otel/v1/traces` | OTLP 摄入（按部署接入约定） |
| `/v1/auth/refresh` | HTTP-only Cookie `refresh_token` |

API key 作用域分三类，签发时前缀区分：全局 `chm_` / 应用 `app-` / 知识库 `kbs-`。
key 隐含应用身份（Dify 套路）——app-scoped key 直接定位绑定的应用，global key 需在 body 显式带 `agent_key`。

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

### GET /v1/auth/me

返当前 JWT 对应用户视图。

### POST /v1/auth/change-password

```json
{ "old_password": "...", "new_password": "..." }
```

首次登录强制改密走 `POST /v1/auth/first-change-password`。

## 二、Agent invoke（业务方调用）

对外服务调用统一靠 `Authorization: Bearer <api-key>` + 扁平路径，key 即应用身份。

### POST /v1/invoke

```http
POST /v1/invoke
Authorization: Bearer <api-key>
Content-Type: application/json
```

```json
{
  "input": "你好",
  "session_id": "optional-session-id",
  "user": "external-end-user-id",
  "agent_key": "qwen-chat",
  "stream": false,
  "attachments": [],
  "context": {},
  "options": {}
}
```

字段说明：

- `input`：`str` → 取 session 历史；`list`（`{role, content, ...}`）→ 客户端自管历史。
- `session_id`：缺省 → 新建会话，响应回显新 ID；传入续接（须同 agent + 同 `user`）。
- `user`：终端用户外部标识（接入方维护的不透明字符串，对应 Dify / OpenAI 协议的 `user`），用于会话归属、历史隔离、按用户统计。
- `agent_key`：仅 global 作用域 key 需要；app-scoped key 不传或填与 `scope_ref` 同值。
- `attachments`：本次调用附带的文件（图片走多模态；文档/数据走临时 RAG）。
- `stream`：`true` → SSE；`false` → 单次 JSON。

非流式响应：

```json
{
  "code": 0,
  "data": {
    "session_id": "abc123",
    "request_id": "req-xxx",
    "answer": "你好！有什么可以帮你的？",
    "steps": [],
    "citations": [],
    "tool_calls": [],
    "usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 }
  }
}
```

流式响应（`stream: true`）：返回 `text/event-stream` SSE：

```
data: {"type":"delta","data":{"text":"你好"}}
data: {"type":"delta","data":{"text":"！"}}
data: {"type":"done","data":{"session_id":"abc123"}}
```

### GET /v1/info

返当前 key 绑定的应用信息（Dify `GET /info` 等价）：`scope_type` / `agent` / `name`。

### POST /v1/chat/completions（OpenAI 兼容）

`model` 字段取 agent_key；`stream=true` → SSE chunk + `[DONE]`。可让 `openai-python` 直接换 `base_url` 与 `api_key` 接入。

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:7009/v1", api_key="chm_...")
resp = client.chat.completions.create(
    model="qwen-chat",
    messages=[{"role": "user", "content": "你好"}],
)
```

## 三、嵌入式 Widget API（公开）

前缀 `/v1/embed/{embed_key}/*`，不走 JWT；服务端校验请求头 `Origin` 是否在 `allowed_origins` 白名单，调用态靠 session_token。

### GET /v1/embed/{embed_key}/config

```json
{
  "code": 0,
  "data": {
    "embed_key": "abc123",
    "name": "官网客服",
    "description": "...",
    "ui_config": { "title": "...", "primary_color": "#0ea5e9" },
    "behavior": { "welcome_message": "...", "placeholder": "...", "show_citations": true },
    "session_policy": { "identification_mode": "anonymous", "show_history_sidebar": false }
  }
}
```

`session_policy` 只暴露 widget 需要的开关（身份模式 / 历史侧栏 / 自动续接等）；签名密钥等机密字段后端持有、绝不下发。

### POST /v1/embed/{embed_key}/session

颁 session_token（Redis 短 TTL），后续 `invoke` 用。可选 body 按 `session_policy.identification_mode` 解析终端用户身份（`device_id` / `external_user_id` / `jwt_token`）并绑到 token；不传 body 时返回未绑用户的 token（向后兼容）：

```json
{ "session_token": "...", "expires_in": 3600 }
```

### POST /v1/embed/{embed_key}/invoke

```json
{ "session_token": "...", "input": "你好", "attachments": [] }
```

```json
{ "code": 0, "data": { "answer": "...", "session_id": "...", "request_id": "..." } }
```

### POST /v1/embed/{embed_key}/invoke/stream

同 invoke，返回 `text/event-stream` SSE。

### 其余 widget 端点

- 会话历史：`GET /v1/embed/{embed_key}/sessions` · `GET /v1/embed/{embed_key}/sessions/{id}/messages`（按 session_token 解析 end_user 隔离）。
- 会话文件：`POST /v1/embed/{embed_key}/files/presigned-upload` · `POST /v1/embed/{embed_key}/files/{object_id}/finalize`（按 `behavior` 校验大小/类型）。
- 追问建议：`GET /v1/embed/{embed_key}/.../followups`。
- 反馈打分：`POST /v1/embed/{embed_key}/feedback`。

## 四、公开数据 API

携带 `Authorization: Bearer <api-key>`，按 key 作用域访问。

### 会话（Sessions）

```
GET  /v1/sessions                          # 列表（按 agent / end_user 过滤）
GET  /v1/sessions/{session_id}             # 详情
GET  /v1/sessions/{session_id}/messages    # 消息分页
POST /v1/sessions/{session_id}/delete      # 删除
```

### 知识库（KB，kbs- 作用域 key）

```
GET  /v1/kb                                 # 知识库元信息
POST /v1/kb/update
POST /v1/kb/delete
POST /v1/kb/documents                       # 投递文档（异步 ingest）
GET  /v1/kb/documents                       # 文档分页
GET  /v1/kb/documents/{doc_id}
POST /v1/kb/documents/{doc_id}/update
POST /v1/kb/documents/{doc_id}/delete
POST /v1/kb/search                          # hybrid 检索（vector + BM25 + RRF + reranker）
```

### 文件

```
POST /v1/files/presigned-upload             # 申请预签名上传 URL
POST /v1/files/{object_id}/finalize         # 上传完成回执
```

### 任务

```
GET  /v1/tasks/{task_id}                     # 异步任务状态查询
```

### OTLP 摄入

```
POST /v1/otel/v1/traces                      # OpenTelemetry trace 上报（OTLP/HTTP）
```

## 五、Admin API（节选）

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
```

### API Key

API key 归属作用域（app / agent / kb），key 隐含其访问身份。创建时返回明文 token，仅一次。

```
GET    /v1/admin/api-keys                  # 分页列表（仅回显前缀）
POST   /v1/admin/api-keys                  # 创建（返回明文 token，仅一次）
POST   /v1/admin/api-keys/{id}/revoke      # 吊销
```

### 应用模板

```
GET    /v1/admin/app-templates
GET    /v1/admin/app-templates/{id}
POST   /v1/admin/app-templates
POST   /v1/admin/app-templates/{id}/update
POST   /v1/admin/app-templates/{id}/delete
```

### 工作流（Graphs）

```
GET    /v1/admin/graphs
POST   /v1/admin/graphs
POST   /v1/admin/graphs/{id}/update
...
```

### 知识库 / 数据集 / 评测

```
GET    /v1/admin/kbs
GET    /v1/admin/datasets
GET    /v1/admin/eval-jobs
GET    /v1/admin/eval-templates
GET    /v1/admin/scores
```

### 嵌入式配置

```
GET    /v1/admin/embed-configs
POST   /v1/admin/embed-configs
POST   /v1/admin/embed-configs/{id}/update
POST   /v1/admin/embed-configs/{id}/delete
```

### 可观测（Trace / Session）

`call_logs` 是 trace 的唯一真相源；前端拆 Trace（单次运行）· Session（会话 thread）两 tab。

```
GET    /v1/admin/call-logs                       # 分页 + 多维过滤
GET    /v1/admin/call-logs/{id}                  # 详情含 spans + payload
GET    /v1/admin/call-logs/{request_id}/tree     # 嵌套 observation trace 树
GET    /v1/admin/sessions                        # 会话（ChatSession）维度列表
```

### 审计日志 / Dashboard

```
GET    /v1/admin/audit-logs             # 分页
GET    /v1/admin/dashboard/overview     # 概览数字 + 曲线 + top-N
GET    /v1/admin/dashboard/timeseries
GET    /v1/admin/dashboard/cost/totals  # 成本汇总
```

### 配置导入导出

```
POST   /v1/admin/settings/export        # 下载 zip
POST   /v1/admin/settings/import        # 上传 zip（multipart/form-data）
```

## 六、SDK

对外契约稳定，可直接 HTTP 调用，也可用官方 SDK：

- **Python**：`pip install chameleon-sdk`（httpx sync + async；`@trace` 装饰器、`patch_openai` / `patch_all` 自动埋点）
- **TypeScript / Node.js**：`npm install @chameleon/sdk`
- **OpenAI 协议层**：兼容 `/v1/chat/completions`，`openai-python` 直接换 `base_url` 即可接入
- **遥测**：OTLP/HTTP 上报到 `/v1/otel/v1/traces`，trace 接入 call_logs 统一观测

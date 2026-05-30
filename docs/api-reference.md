# Chameleon Service API 参考（Dify 风扁平契约）

> 2026-05-28 重构后的对外服务 API。**key 即应用身份**——`Authorization: Bearer xxx` 已经唯一标识了"这个 key 代表的应用"和"这个 key 能看到的会话/日志"，路径不再带 `agent_key` 占位。

## 1. 基础

```
Base URL:  https://<your-host>
Auth:      Authorization: Bearer <api-key>
```

### Key 作用域（决定 key 能做什么）

| `scope_type` | 含义 | invoke / sessions 行为 |
|---|---|---|
| `app` | 绑定到具体应用（`scope_ref` = `agent_key`） | 路径中**不带** `agent_key`；调用/列会话自动锁定到 scope_ref |
| `global` | 通吃所有应用 | invoke 时 body 需带 `agent_key`；会话可按 `agent_key` 过滤 |
| `kb` | 仅知识库（不能调 invoke） | 用于 `/v1/kb/*` 公开 API；key 即 KB 身份 |

前缀约定（生成时给的，校验靠 hash）：app 前缀 `app-`，global 前缀 `chm_`，kb 前缀 `kbs-`。

## 2. 应用调用

### 2.1 POST `/v1/invoke` —— 调用应用（推荐）

```bash
POST /v1/invoke
Authorization: Bearer app-xxxx
Content-Type: application/json

{
  "input": "你好，介绍一下你自己",
  "session_id": null,            // 可选：续接已有会话
  "user": "biz-user-12345",      // 可选：终端用户外部 id（按用户隔离 + 计费）
  "stream": false,               // true → SSE
  "context": {},                 // 业务上下文
  "options": {}                  // provider-specific 运行时覆盖
}
```

**响应（非流）**

```json
{
  "code": 0,
  "success": true,
  "data": {
    "session_id": "sess_abcd1234",
    "request_id": "req_xxx",
    "answer": "你好！我是...",
    "steps": [],
    "citations": [],
    "tool_calls": [],
    "usage": { "prompt_tokens": 123, "completion_tokens": 456, "total_tokens": 579 }
  }
}
```

**流式响应**（`stream: true`）：SSE `data: {...}\n\n` 事件流，最终 `data: [DONE]\n\n`。事件类型见各 provider 文档。

**全局 key 调用法**：body 加 `agent_key` 字段指定目标应用。app-scoped key 不需要（带了会校验必须 = scope_ref）。

### 2.2 GET `/v1/info` —— 当前 key 代表的应用

```bash
GET /v1/info
Authorization: Bearer app-xxxx
```

返：

```json
{
  "data": {
    "scope_type": "app",
    "agent": {
      "key": "demo-chat-xiaochai",
      "provider": "graph",
      "description": "...",
      "version": "1.0",
      "tags": []
    },
    "name": "小柴的 Web App"
  }
}
```

global key 调时 `agent` 为 null（因为它不绑特定应用）。

### 2.3 POST `/v1/chat/completions` —— OpenAI 兼容

```bash
POST /v1/chat/completions
Authorization: Bearer app-xxxx

{
  "model": "demo-chat-xiaochai",  // = agent_key，app-scoped key 时也建议带
  "messages": [{ "role": "user", "content": "hi" }],
  "stream": true,
  "user": "biz-user-12345"        // OpenAI 协议原生字段
}
```

任何 OpenAI 客户端 SDK 都能直接接入。

## 3. 会话管理（key 已隐含归属，无需再传 agent_key）

| 端点 | 用途 |
|---|---|
| `GET /v1/sessions?user=xxx&page=1&page_size=10` | 列当前 key 范围内的会话；可按终端用户过滤；app-scoped key 自动锁 agent |
| `GET /v1/sessions/{session_id}` | 详情 |
| `GET /v1/sessions/{session_id}/messages` | 该会话消息分页 |
| `POST /v1/sessions/{session_id}/delete` | 软删 |
| `POST /v1/sessions/{session_id}/messages/{message_id}/regenerate` | 重新生成 assistant（分支） |
| `POST /v1/sessions/{session_id}/messages/{message_id}/edit-and-resend` | 编辑 user 重发（兄弟分支） |

**security**：普通 key 只能看到自己 `app_id` 来源的会话；app-scoped key 进一步只能看到 scope_ref 对应 agent 的会话。

## 4. 嵌入应用专属（origin + session_token）

嵌入应用是另一条公开渠道（origin 白名单 + 短期 session_token，无需 Bearer key），见 [embed-integration-guide.md](./embed-integration-guide.md)。

## 5. 知识库 API（Dify 风扁平契约）

**key 即 KB 身份**——`kbs-` 前缀的 key 已经唯一绑定到一个知识库，路径中不再带 `kb_key` 占位。
管理后台按 `kb_id` 走 `/v1/admin/kbs/*`（JWT 鉴权），这里只列业务方用的公开 API。

### 5.1 GET `/v1/kb` —— 当前 key 代表的知识库

```bash
GET /v1/kb
Authorization: Bearer kbs-xxxx
```

返：

```json
{
  "data": {
    "id": 12,
    "kb_key": "demo-faq",
    "name": "产品 FAQ",
    "description": "...",
    "embedding_model": "text-embedding-3-small",
    "embedding_dim": 1536,
    "chunk_size": 800,
    "chunk_overlap": 100,
    "chunk_strategy": null,
    "created_at": "...",
    "updated_at": "..."
  }
}
```

global key 调时 query 加 `?kb_key=xxx` 指定目标 KB（kb-scoped key 不需要、带了会校验必须 = scope_ref）。

### 5.2 POST `/v1/kb/search` —— 检索

```bash
POST /v1/kb/search
Authorization: Bearer kbs-xxxx
Content-Type: application/json

{
  "query": "如何重置密码",
  "top_k": 5,
  "min_score": 0.0
}
```

返命中切块数组（带 score / meta）。

### 5.3 文档增改删查

| 端点 | 用途 |
|---|---|
| `GET /v1/kb/documents?page=1&page_size=20` | 列文档 |
| `GET /v1/kb/documents/{doc_id}` | 详情 |
| `POST /v1/kb/documents` | 创建文档（异步入库，返 task_id 轮询状态） |
| `POST /v1/kb/documents/{doc_id}/update` | 改 title / tags / meta（不重分块） |
| `POST /v1/kb/documents/{doc_id}/delete` | 软删 + 清切块/向量 |

**创建文档**示例：

```bash
POST /v1/kb/documents
Authorization: Bearer kbs-xxxx

{
  "title": "产品 FAQ",
  "source_type": "text",            // text | url
  "content": "问：...\n答：..."     // source_type=text 必填；url 时传 source_uri
}
```

### 5.4 KB 元信息 / 删除（谨慎）

| 端点 | 用途 |
|---|---|
| `POST /v1/kb/update` | 改 name / description / chunk_size / chunk_overlap / chunk_strategy |
| `POST /v1/kb/delete` | 软删 KB（不删 documents/chunks，由 admin 手工清扫） |

> **KB 创建 / 列表** 不在公开 API —— 走管理后台 `/v1/admin/kbs/*`（JWT 鉴权）。

## 6. 调用流量归属

每条 `call_logs` 行带的归属字段（按 key 维度做统计/计费）：

| 字段 | 含义 |
|---|---|
| `api_key_id` | 这次调用用的 key 的 id |
| `app_id` | key 的来源标签 |
| `agent_key` | 实际命中的应用 |
| `end_user_id` | body.user（终端用户外部 id） |
| `channel` | api / openai / embed / playground / internal |
| `session_id` | 会话 id |

按 key 聚合（推荐）：
```sql
SELECT SUM(cost_usd), SUM(total_tokens), COUNT(*)
FROM call_logs
WHERE api_key_id = ? AND created_at > now() - INTERVAL '7 days'
GROUP BY DATE(created_at);
```

按终端用户聚合：
```sql
SELECT SUM(cost_usd) FROM call_logs
WHERE api_key_id = ? AND end_user_id = ?;
```

## 7. 错误码常见

| code | name | 说明 |
|---|---|---|
| 0 | Success | 成功 |
| 40300 | PermissionDenied | 没权限（含 origin 白名单 / scope 越权） |
| 40402 | SessionNotFound | session_id 不存在或越权 |
| 40004 | ValidationError | 入参格式错；全局 key 缺 agent_key；session 跨 agent 续接 |
| ApiKeyRevoked | — | key 已吊销 |
| AppRateLimit | — | 频率超限（key.qpm_limit / qpd_limit） |
| 500 | InternalError | 服务异常 |

---

**相关后端文件**

- `chameleon-api/.../agent/api.py` — `flat_router`：POST `/v1/invoke` + GET `/v1/info`
- `chameleon-api/.../knowledge/api.py` — KB 扁平 API：GET `/v1/kb` + 文档增改删查 + 检索
- `chameleon-api/.../sessions/api.py` — 会话管理；自动按 key.scope_ref 锁定
- `chameleon-api/.../openai/api.py` — OpenAI 兼容
- `chameleon-integrations/.../observe/llm_recorder.py` — generation 行自动落账
- `chameleon-data/.../infra/auth.py` — `CurrentApp` + key scope 解析

**Plan**: `docs/plans/2026-05-28-session-and-observability-refactor.md`

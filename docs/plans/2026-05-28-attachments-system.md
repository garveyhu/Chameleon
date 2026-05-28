# 附件上传系统 · 总体设计

> 一次性把"AI 对话传文件"全套打通：图片多模态 + 长文件临时 RAG + 数据文件代码沙箱 + 工作流文件变量 + agentkit 接口。
>
> 业界对照：ChatGPT「上传文件」（按类型自动分流到 vision / RAG / Code Interpreter） + Dify「文件输入变量」（工作流场景）。

---

## 0. 目标

| 应用类型 | 用户传图片 | 传 PDF/DOCX/MD | 传 CSV/XLSX | 传任意 URL |
|----------|-----------|----------------|-------------|-----------|
| **嵌入式 widget** | LLM 视觉直读 | 临时 KB + RAG | (Phase C) 沙箱 | — |
| **Service API** | body.attachments | body.attachments | body.attachments | — |
| **工作流** | file 变量 → LLM/KB 节点 | file 变量 → KB 节点切块 | file 变量 → Code 节点挂载 | HTTP 节点 |
| **代码型（agentkit）** | `ctx.attachments[i].url` | 同上 | 同上 | 同上 |
| **OpenAI 兼容** | messages[].content multimodal | (跳过) | (跳过) | — |

---

## 1. 数据模型变更

### 1.1 `session_files` 表（新）

记录会话上下文中的附件：

```sql
session_files
  id             BIGINT PK
  session_id     VARCHAR FK→sessions.session_id  -- 绑会话
  object_url     TEXT      -- presigned long-lived URL（24h）
  object_id      VARCHAR   -- MinIO 内部 key（删除时用）
  filename       VARCHAR
  mime           VARCHAR
  size           BIGINT
  kind           VARCHAR   -- 'image' | 'document' | 'data' | 'audio' | 'other'
  ephemeral_kb_id BIGINT FK→kbs.id NULL  -- document 类型时切块入这个临时 KB
  status         VARCHAR   -- 'uploaded' | 'parsing' | 'ready' | 'failed'
  error          TEXT NULL
  created_at     TIMESTAMP
```

### 1.2 `kbs` 表加 `kind` 字段（区分常规 KB 与临时 KB）

```sql
ALTER TABLE kbs ADD COLUMN kind VARCHAR(16) NOT NULL DEFAULT 'normal';
-- 'normal' = 常规 KB；'ephemeral_session' = 会话临时 KB
```

临时 KB 不出现在 KB 列表里，自动随 session 软删而清理。

### 1.3 `messages` 表已有 `extra_meta` JSON

把附件附加在用户消息上：`extra_meta.attachments = [{ object_url, filename, mime, kind }, ...]`，历史回放能看到。

---

## 2. API 契约

### 2.1 上传端点（已有）

`POST /v1/files/presigned-upload` —— 三步流程：
1. presigned PUT URL
2. 客户端 PUT MinIO
3. `POST /v1/files/{object_id}/finalize` 获取长效 GET URL

### 2.2 invoke 加 `attachments`

**Service API**（`POST /v1/invoke`）：
```json
{
  "input": "这张图什么意思",
  "attachments": [
    {"object_url": "https://...", "filename": "x.png", "mime": "image/png", "size": 123456}
  ],
  "session_id": null,
  "user": "..."
}
```

**Embed**（`POST /v1/embed/{key}/invoke[/stream]`）：同上加 attachments 字段。

**OpenAI 兼容**（`/v1/chat/completions`）：走标准 multimodal `messages[i].content` 数组协议（图片用 `image_url` block，其他类型暂不支持以保兼容）。

### 2.3 invoke 端点的处理流程

```
1. service 拿到 attachments
2. 按 mime 分类：
   - image/* → 直接转 ImageUrlBlock，进当前 turn 的 multimodal message
   - audio/* → AudioUrlBlock
   - application/pdf | text/* | docx/markdown → 异步切块入 session 的 ephemeral_kb
                                                  + 当前 turn 提示"已附加文档"
   - csv/xlsx | application/octet-stream → Phase C：标记为 data，让 Code 节点取
3. 写入 session_files 表（status='uploaded' → 'parsing' → 'ready'/'failed'）
4. 把 attachments 元数据塞进 messages.extra_meta（历史回放用）
5. 当前 turn 拼 prompt 时：
   - vision LLM：multimodal message
   - 有 ephemeral_kb：自动检索附加到 prompt 上下文
6. 流式响应里照常带 citation；source 字段标注是哪个上传文件
```

### 2.4 widget 拿"已上传文件列表"

`GET /v1/embed/{key}/sessions/{sid}/files?session_token=...` → `[SessionFileItem]`

`POST /v1/embed/{key}/sessions/{sid}/files/{file_id}/delete` → 从会话移除（同步删 ephemeral_kb 里对应文档）

---

## 3. UI 流程

### 3.1 嵌入式 widget

1. composer 上"回形针"按钮（受 `behavior.allow_file_upload` 控制） → 文件选择器
2. 选完文件 → presigned-upload 三步 → 上传完成后在 composer 上方显示**附件 chip**：
   ```
   [📷 screenshot.png ✕]  [📄 contract.pdf · 解析中... ✕]
   ```
3. 发消息时 chip 跟着发出去，**消息气泡里也展示附件缩略**（图片缩略图、文档图标 + 文件名）
4. assistant 回复带 citation 时，如果 source 是上传文件 → 引用块里展示"来自 contract.pdf 第 N 段"
5. 重新打开历史会话时 → `GET /sessions/{sid}/files` 拿到该会话曾上传过的文件列表，可继续问

### 3.2 Web App（公开应用页 + 编辑器调试）

跟 widget 同一套 UX，多一个"附件管理"侧栏（看本会话所有已上传文件）。

### 3.3 工作流编辑器（Phase C）

- 起点节点 inspector 加「文件输入」类型字段：可声明 `files: file[]` 输入
- 调试面板加文件上传 → 走标准 attachments → graph runtime 把文件作为变量传给下游节点
- LLM 节点 inspector 勾选「接收文件」→ 自动以 multimodal 形式拼 prompt
- KB 节点 inspector 勾选「使用临时 KB」→ 自动建临时 KB + 切块入
- Code 节点 inspector 勾选「挂载文件到沙箱」→ sandbox 启动时 mount

---

## 4. agentkit（Phase C）

```python
from chameleon_agentkit import agent, AgentContext

@agent
async def my_helper(query: str, ctx: AgentContext):
    for att in ctx.attachments:
        if att.kind == "image":
            return await ctx.llm.invoke([
                ImageUrlBlock(image_url=att.url),
                TextBlock(text=query),
            ])
        elif att.kind == "document":
            # 临时 KB 已经在 ctx.kb 里挂上了
            chunks = await ctx.kb.search(query)
            return await ctx.llm.invoke(prompt_with_chunks(query, chunks))
    return await ctx.llm.invoke(query)
```

---

## 5. 实施阶段

### Phase A · 图片多模态 (1-2 天)
| 任务 | 内容 |
|------|------|
| A-1 | 后端：`invoke` 入参加 `attachments`（schemas + agent.service） |
| A-2 | 后端：agent.service 按 mime 分流；图 → ImageUrlBlock 拼进 multimodal message |
| A-3 | 后端：messages.extra_meta 落 attachments；历史回放 |
| A-4 | 前端 widget：`.upload-btn` 接事件 + 选择文件 + 三步上传 + chip 显示 + 发消息带 attachments |
| A-5 | 前端 widget：消息气泡渲染附件缩略图 |
| A-6 | 嵌入 invoke / invoke/stream 端点同步加字段 |
| A-7 | 文档站 invoke 端点说明加 attachments 字段 |
| A-8 | tsc/build/浏览器验证 |

### Phase B · 长文件临时 RAG (5-7 天)
| 任务 | 内容 |
|------|------|
| B-1 | DB 迁移：`session_files` 表 + `kbs.kind` 字段 |
| B-2 | ORM：SessionFile + Kb.kind |
| B-3 | 复用 KB-A 切块流程，封装 `ephemeral_kb_service`：upload → parsing → 切块入 |
| B-4 | agent.service：检测当前 session 有 ephemeral_kb 时自动 RAG 检索 + 拼 prompt |
| B-5 | citation 透出 source（哪个上传文件、第 N 段） |
| B-6 | embed 端点：`GET/POST /sessions/{sid}/files` 列/删 |
| B-7 | widget 上传 PDF/DOCX 显示"解析中" 状态、轮询 status 切到"已就绪"再可发送 |
| B-8 | 会话软删时级联清 ephemeral_kb（migration 不操心，业务层处理） |

### Phase C · 工作流 + agentkit + 沙箱 (5-7 天)
| 任务 | 内容 |
|------|------|
| C-1 | 工作流变量系统加 `file` / `file[]` 类型 |
| C-2 | palette 起点节点输入 schema 支持 file |
| C-3 | LLM 节点：multimodal 适配（image 进 message） |
| C-4 | KB 节点：临时 KB 模式（接受 file 输入切块） |
| C-5 | Code 节点：sandbox mount 文件 |
| C-6 | HTTP 节点：把 file URL 透传 body |
| C-7 | agentkit `ctx.attachments` API |
| C-8 | 编辑器调试面板加文件上传 |

---

## 6. 关键决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 图片是否进 RAG | ❌ 不进 | vision 直读快、准、便宜（不需要 OCR + chunk + embed） |
| 临时 KB 是新表还是复用 kbs 表加字段 | **复用 `kbs.kind`** | 避免双套 chunk/embed 基础设施、自动复用 KB-D 召回 pipeline |
| 临时 KB 怎么清理 | session 软删时业务层清 | 不用 DB 级联（kbs.kind 跟 sessions 没 FK 关系） |
| 附件挂在 user message 还是单独表 | **session_files 表 + messages.extra_meta 冗余** | 表查"会话有哪些文件"快；冗余在 message 上让单条历史回放完整 |
| MinIO URL 是 presigned 长效还是公开 | **presigned 24h GET，过期自动 refresh** | 隐私 + 可吊销 |
| 模型不支持 vision 怎么办 | service 层报"当前模型不支持 vision，请在「模型」tab 选支持 vision 的模型" | model registry 加 `supports_vision: bool` 字段，绝不静默丢弃 |

---

## 7. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 大文件上传 timeout | MinIO 直传 + 前端进度条 + 分片（Phase B+） |
| 临时 KB 数据库爆涨 | session 软删 + 24h 后台清理过期临时 KB |
| PDF 解析失败 / 大量空白页 | failed status + 前端提示用户重传或文本粘贴 |
| 多个文件同时上传时 widget 卡 | upload 走并发 + Promise.allSettled |
| vision 模型 cost 高 | 上传前提示「图片单次成本约 $0.01」，可关 |
| 跨会话误用 | 严格按 session_id 隔离查询 |

---

## 8. 实施 plan

- **本 session 推 Phase A 全套**（A-1 ~ A-8）
- Phase B 单独 plan 起一次（涉及 DB migration，需独立 PR）
- Phase C 起 plan 后单独推进（编辑器侧动作大）

# 会话与可观测重构计划

> 2026-05-28 · 综合 conversations→sessions 重构 + 终端用户身份补齐 + 大模型调用切面收口（LangFuse 式 generation 行） + 嵌入式会话管理产品化

## 0. 背景与诉求

历经多轮讨论暴露了三个相互纠缠的问题，必须一次性做完才能闭环：

1. **会话身份层缺失**：`conversations` 表只挂 `agent_key` + `app_id`（开发者 key 的来源标签），没有「使用这个 app 的终端用户」维度——一个 API key 接出去的所有终端用户会话混在一个池子里，跨端历史、按用户计费、按用户限流全做不了。
2. **大模型调用切面挂错了层**：generation 记录散在 `agent service` / `AgentRun` 等调用方手记，谁绕过谁就丢账（KB 摄入烧 token 零记录）。需要把探针下沉到 `BaseLLM` 对象本身。
3. **嵌入式会话产品化能力缺失**：每次刷新即新对话、无侧栏切换、无显式新建、无 EmbedConfig 配置粒度——比 Dify/FastGPT 差一档。

附带：`session_id` 是事实主键，表却叫 `conversations`——名实不副，借这次重构改名 `sessions`。

## 1. 设计原则

1. **`messages`（业务记忆）与 `call_logs`（监控流水）永远是两本账**，互不替代，别再合并。
2. **切面挂在被调对象（BaseLLM）上**，不挂调用方（AgentRun / agent.service）。归属靠 `ContextVar`-based ambient TraceContext，由入口设置。
3. **generation 这种观测全系统只有一个出生地**：BaseLLM 回调。任何调用方手开 `type='generation'` 的 span 一律拆除（避免双记）。
4. **终端用户身份是会话管理一切功能的前提**：API/嵌入/Web 三端全部按 (App, EndUser, Session) 三层组织，对齐 Dify/FastGPT。
5. **重命名既然要做就一步到位**：drop 老 `conversations` + create 新 `sessions`，类、模块、API 路径同步改名。不留 alias、不做 compat layer——开发期未上生产。

## 2. 数据模型重设

### 2.1 表与列变更总览

| 表 | 操作 |
|---|---|
| `conversations` | **DROP**（drop+create，不迁数据） |
| `sessions` | **CREATE**（新表，承接 conversations 的角色 + 加 `end_user_id` / `key_id` / `model_code` 等） |
| `messages` | ALTER：`session_id` 保留；加 `end_user_id`（冗余）；不动 schema 外其他 |
| `call_logs` | ALTER：加 `end_user_id` 列（冗余，按用户分析免 join）；`api_key_id`/`key_scope` 已有；保留 |
| `embed_configs` | ALTER：加 `api_key_id` FK（绑 owner key，决策点 D2）；加 `session_policy` JSON；`behavior` 字段保留作其他行为开关 |
| `end_users` | **不建独立表**（KISS）。`end_user_id` 是接入方提供的不透明字符串。需要 metadata 时再加。 |

### 2.2 `sessions` 表 schema（DDL 草图）

```sql
CREATE TABLE sessions (
    id            BIGINT PRIMARY KEY,                -- 内部雪花 PK
    session_id    VARCHAR(64) NOT NULL UNIQUE,       -- 对外 id（保留 sess_ 前缀）
    agent_key     VARCHAR(64) NOT NULL,              -- 关联的应用（agent_key 或 graph_key）
    app_id        VARCHAR(64) NOT NULL,              -- key 来源标签（保留，独立维度）
    api_key_id    BIGINT NULL REFERENCES api_keys(id),-- 发起方 key（决策点 D2 影响）
    end_user_id   VARCHAR(128) NULL,                 -- 终端用户外部 id（核心新增）
    title         VARCHAR(255) NULL,
    last_message_at  TIMESTAMPTZ NULL,
    provider_conv_id VARCHAR(255) NULL,              -- 第三方 provider 会话 id（沿用）
    meta          JSONB NULL,                        -- 扩展位
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at    TIMESTAMPTZ NULL                    -- 软删
);

CREATE INDEX ix_sessions_agent_key       ON sessions(agent_key);
CREATE INDEX ix_sessions_app_id          ON sessions(app_id);
CREATE INDEX ix_sessions_end_user_id     ON sessions(end_user_id);
CREATE INDEX ix_sessions_last_message_at ON sessions(last_message_at DESC NULLS LAST);
CREATE INDEX ix_sessions_app_user        ON sessions(app_id, end_user_id, last_message_at DESC); -- 列表热查
```

### 2.3 `messages` / `call_logs` 增量

```sql
ALTER TABLE messages   ADD COLUMN end_user_id VARCHAR(128) NULL;
ALTER TABLE call_logs  ADD COLUMN end_user_id VARCHAR(128) NULL;
CREATE INDEX ix_messages_session_seq    ON messages(session_id, seq);     -- 应已存在，确认
CREATE INDEX ix_call_logs_end_user_id   ON call_logs(end_user_id);
```

### 2.4 `embed_configs` 扩展

```sql
ALTER TABLE embed_configs ADD COLUMN api_key_id BIGINT NULL REFERENCES api_keys(id);
ALTER TABLE embed_configs ADD COLUMN session_policy JSONB NULL;
```

`session_policy` 结构（不强约束，反序列化时 Pydantic 校验）：

```json
{
  "identification_mode": "anonymous_device",     // anonymous_device / external_user_id / signed_jwt
  "jwt_signing_secret_id": null,                  // 仅 signed_jwt 模式用，引用密钥管理表
  "show_history_sidebar": true,
  "auto_resume_last": true,
  "allow_user_manage": true,                      // 是否允许 end-user 改名/删会话
  "max_history_days": 90
}
```

## 3. 切面架构（generation 收口）

### 3.1 收口前的问题

| 现状 | 位置 | 问题 |
|---|---|---|
| `agent.service` 末尾手记 root CallLog | `chameleon-api/.../agent/service.py:254` | 只在 agent.invoke 闭环时记，KB 摄入这类绕过的丢账 |
| `AgentRun.complete/stream` 包 `type='generation'` span | `chameleon-agentkit/.../_runtime.py:120/137` | 调用方手开 generation，与未来下沉到 BaseLLM 的回调**会双记** |
| `SpanRecorder` 通过函数参数手传 | `chameleon-core/.../utils/spans.py` + agent service | 不是 ambient context，外部模块拿不到 |
| `observe/context.py` 的 ContextVar 已建但没接 | `chameleon-core/.../observe/context.py` | 基础设施在，没被 agent service 用上 |

### 3.2 新架构

**核心**：探针在对象上 + 归属在 ContextVar。

```
入口（agent.invoke / embed / agentkit transport / KB 摄入）
   │
   ├─ 开 trace scope：把 TraceContext 写进 ContextVar
   │     TraceContext(request_id, app_id, key_id, channel,
   │                  agent_key, session_id, end_user_id, parent_id)
   │
   └─ 业务执行 → 任意路径拿到 BaseLLM → .ainvoke()/.astream()
         │
         └─ LangChain on_llm_end 触发 GenerationRecorder
               ├─ 读 LLMResult → usage / 输入快照 / 输出快照
               ├─ 读 ContextVar → app_id / key_id / end_user_id / parent_id
               ├─ 算 cost（模型单价表）
               └─ 落 call_logs 一行 observation_type='generation'
                  （冗余 app_id/key_id/end_user_id/channel 进列）
```

**关键点**：
- 模型实例进程级共享缓存（`LLMFactory._CACHE`），**不能**往实例上塞请求级状态——归属一律走 ContextVar。
- 入口外没开 scope 也不丢账：ContextVar 为空时 `GenerationRecorder` 兜底写 `channel='internal'` 的独立 generation 行。

### 3.3 调用方切面拆除清单（避免双记）

| 拆什么 | 文件 | 改成什么 |
|---|---|---|
| `AgentRun.complete/stream` 的 `span("llm.*", type="generation")` | `chameleon-agentkit/.../_runtime.py:120/137` | 删除（或降级为 `type="span"` 纯计时） |
| Graph LLMNode/Classifier 手开 generation | `chameleon-core/.../graph/nodes/llm.py`, `classifier.py` | 删除任何 generation 类型 span |
| agent.service 末尾的 `_record_call`（root） | `chameleon-api/.../agent/service.py:254` | 保留，但 `observation_type='trace'`（请求根），不与 generation 冲突 |
| `SpanRecorder` 手传参数 | agent.service / provider.service | 改成 ambient（ContextVar 里持有当前请求的累加器），生命周期由入口管理 |

### 3.4 兜底场景

| 场景 | 处理 |
|---|---|
| KB 摄入（QA 生成）裸调 `resolve_llm()` | ContextVar 空 → GenerationRecorder 自起短 session 写一条 `channel='internal'`、`app_id='kb-ingest'`、`end_user_id=NULL` 的 generation 行 |
| Playground 调试 | 入口主动开 scope `channel='playground'`，按业务策略可选**不**记入 call_logs（保留现有"调试不污染统计"原则，但用 scope 显式控制而非靠绕过）|
| 模型连通性测试 | admin 工具，主动开 scope `channel='admin-test'` 或 explicit skip flag |

### 3.5 工厂注入

```python
# chameleon-core/.../components/llms/factory.py  reload_llm_cache
from chameleon.core.observe.llm_recorder import GenerationRecorder

instance = BaseLLM(
    model=model.code,
    api_key=api_key,
    api_base=api_base,
    callbacks=[GenerationRecorder(model_code=model.code, pricing=model.pricing)],
    ...
)
```

Pricing 来源：`models` 表新增 `pricing` JSON 字段（`{"input_per_1k": 0.001, "output_per_1k": 0.002}`）；或独立 `model_pricing` 表（决策点 D4）。

### 3.6 LangChain async ContextVar 视性

实测点：`AsyncCallbackHandler` 在 `await chat.ainvoke()` 触发的 `on_llm_end` 必须能读到入口设置的 ContextVar。退路：入口处同时将 TraceContext 塞进 `ainvoke(config={"metadata": ...})`，回调从 `metadata` 读——但优先 ContextVar，调通就不用退路。

## 4. API 接口设计

### 4.1 `/v1/sessions/*`（替代 `/v1/conversations/*`，路径换名同步）

| 端点 | 方法 | 鉴权 | 说明 |
|---|---|---|---|
| `/v1/sessions` | GET | api_key | 列会话；过滤 `agent_key` / `user` / `app_id`；普通 key 仅看 (own app_id + 传入 user) |
| `/v1/sessions/{session_id}` | GET | api_key | 详情 |
| `/v1/sessions/{session_id}/messages` | GET | api_key | 该会话消息分页 |
| `/v1/sessions/{session_id}/delete` | POST | api_key | 软删 |
| `/v1/sessions/{session_id}/name` | POST | api_key | 手动改名 |
| `/v1/sessions/{session_id}/messages/{message_id}/regenerate` | POST | api_key | 已有分支能力，迁移过来 |
| `/v1/sessions/{session_id}/messages/{message_id}/edit-and-resend` | POST | api_key | 同上 |

`/v1/agents/{key}/invoke` 入参 `InvokeRequest` 加 `user: str | None`（终端用户外部 id），透传至 `_ensure_conversation`。

`/v1/chat/completions`（OpenAI 兼容）增加从 request body 取 `user`（OpenAI 协议本身就有这个字段，免破坏兼容）。

### 4.2 嵌入式补端点（`/v1/embed/{embed_key}/...`）

| 端点 | 方法 | 用途 |
|---|---|---|
| `/sessions` | GET | 当前 end_user 的历史会话列表 |
| `/sessions/{session_id}/messages` | GET | 切到旧会话，加载消息 |
| `/sessions/new` | POST | 显式开新会话（不靠刷新；返回新 session_token + session_id） |
| `/sessions/{session_id}/delete` | POST | end-user 删除自己的会话（受 `allow_user_manage` 限制） |
| `/sessions/{session_id}/name` | POST | 改名（同上限制） |

`POST /session`（颁发 token）扩展：按 `identification_mode` 接受不同入参——
- `anonymous_device`: 前端传持久化 device_id；后端 hash 后当 end_user_id
- `external_user_id`: 接入方在嵌入脚本里直接传字符串 user_id
- `signed_jwt`: 接入方传 JWT，后端用 `jwt_signing_secret_id` 对应的密钥验签，从 payload 取 `sub` 当 end_user_id

## 5. EmbedConfig.session_policy 行为

| 配置项 | 默认 | 影响 |
|---|---|---|
| `identification_mode` | `anonymous_device` | 决定 session token 颁发流程 |
| `show_history_sidebar` | `true` | 嵌入 widget 是否显示左侧会话列表 |
| `auto_resume_last` | `true` | widget 加载时是否自动续接 localStorage 里的 last_session_id |
| `allow_user_manage` | `true` | 是否显示删除/改名按钮 + 对应 API 是否对该 embed 启用 |
| `max_history_days` | `90` | 列表查询时间窗（不影响 DB 留存） |

## 6. 前端工作

### 6.1 嵌入 widget 改造

- `localStorage` 持久化：`device_id`（首次随机生成）+ `last_session_id`
- 启动按 `session_policy.auto_resume_last` 决策续接或新开
- 侧栏（`show_history_sidebar` 控制）：列出历史会话、新建按钮、长按改名删除
- "+" 按钮调 `POST /sessions/new` 显式开新对话

### 6.2 后台「应用详情」配置表单

- 在「嵌入式应用」编辑抽屉内加 `session_policy` 块（结构化表单，不是裸 JSON）
- 把现有"嵌入式应用"内的 owner key 选择器加上（决策 D2 = 是）

### 6.3 后台「应用详情 → 会话」tab（新增）

- 列当前 app 下所有会话
- 过滤：按 end_user_id、按时间窗、按 agent_key
- 行内查看消息 + 删除

## 7. 执行块（按依赖顺序）

| 块 | 内容 | 依赖 | 工作量 |
|---|---|---|---|
| **S1** | Alembic 迁移：drop `conversations` + create `sessions` + alter `messages` + alter `call_logs` + alter `embed_configs` | 无 | 小 |
| **S2** | ORM 模型：`Conversation` → `ChatSession`（避免与 SQLA Session 冲突），文件 `conversation.py` → `chat_session.py`；schemas / errors 同步改名 | S1 | 中 |
| **S3** | service 层改名 + end_user_id 全链路：`conv_service` → `session_service`；`_ensure_conversation` → `_ensure_session`；所有调用方传 `end_user_id` 透传 | S2 | 中 |
| **S4** | 扩展 `observe/context.py` 的 ContextVar 为完整 `TraceContext`（带 request_id / app_id / key_id / channel / agent_key / session_id / end_user_id / parent_id） | 无 | 小 |
| **S5** | `GenerationRecorder` 实现（LangChain AsyncCallbackHandler）+ 模型单价表 + cost 计算 + 兜底独立写 | S4 | 中 |
| **S6** | `LLMFactory.reload_llm_cache` 注入 GenerationRecorder | S5 | 小 |
| **S7** | 拆调用方切面：`AgentRun.complete/stream` 删 generation span；graph LLMNode/Classifier 同；`SpanRecorder` 从手传改 ambient | S6 | 中 |
| **S8** | agent.service 重做：开 trace scope（写 TraceContext） + 不再手记 generation（只记 root trace）；test/playground/KB ingest 入口对齐 | S7 | 中 |
| **S9** | `/v1/sessions/*` API 重做（替换 `/v1/conversations/*` 路径）；`InvokeRequest` 加 `user`；OpenAI 兼容端取 `user` | S3 | 中 |
| **S10** | `embed_configs.api_key_id` + `session_policy` 后端服务接入；`/session` 颁发按 identification_mode 分流；signed_jwt 验签 | S1, S3 | 中 |
| **S11** | 嵌入端补端点：`GET /sessions`、`/sessions/{id}/messages`、`POST /sessions/new`、`/delete`、`/name` | S10 | 小 |
| **S12** | 前端 embed widget：localStorage 持久化 + 侧栏 + 续接策略 + 新建按钮 | S11 | 中 |
| **S13** | 后台「嵌入应用」编辑表单：owner key 选择器 + session_policy 结构化表单 | S10 | 小 |
| **S14** | 后台「应用详情 → 会话」tab：列表 + 过滤 + 删除 | S9 | 中 |
| **S15** | 测试：单元（service 层）+ 集成（embed 三种身份模式全链路）+ 浏览器 e2e（嵌入式侧栏切换 / 续接 / 新建） | 所有 | 中 |
| **S16** | 文档：更新嵌入接入文档（带 user 参数说明）+ Session 管理文档 + observability 文档（generation 行说明） | S15 | 小 |

合计 16 块，建议拆给 3 个并行 worktree agent：
- Agent X: S1→S2→S3→S9→S14（数据 + API + 后台 UI）
- Agent Y: S4→S5→S6→S7→S8（切面收口，强一致依赖单线）
- Agent Z: S10→S11→S12→S13（嵌入式 + widget）
- 主线：S15→S16

## 8. 决策点（待确认；plan 默认值已注明）

| # | 问题 | 默认 | 备选 |
|---|---|---|---|
| **D1** | 旧 `conversations` / `messages` 数据保留？ | drop+create，不迁数据（你已说"删掉"） | rename + 加列保留数据 |
| **D2** | `embed_configs` 绑 owner `api_key_id`？ | **是**（解决之前嵌入流量归属问题 + 复用 key 限流） | 否（保持现状免鉴权公开渠道，仅靠 end_user 区分） |
| **D3** | `signed_jwt` 身份模式这一轮做？ | **是**（三模式齐了不返工） | 仅做 `anonymous_device` + `external_user_id`，jwt 留 v2 |
| **D4** | 模型 pricing 落在 `models` 表 JSON 字段 vs 独立 `model_pricing` 表？ | **嵌进 models 表 JSON**（KISS） | 独立表（多供应商比价更整齐） |
| **D5** | Playground 是否落 call_logs？ | **不落**（保留"调试不污染统计"原则，scope 写 `channel='playground'` 但显式 skip 写库） | 落，方便回溯调试 |
| **D6** | OpenAI 兼容端点路径是否改？ | **不改**（保留 `/v1/chat/completions`） | 同步迁到 `/v1/sessions/chat/completions`（不推荐，破兼容） |

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| `Conversation` → `ChatSession` 改名涉及全仓 import 大改 | 用 ruff `--fix` + grep 串改；一次成型 PR；务必 tsc/pytest 跑全 |
| LangChain async ContextVar 在 callback 内不可见 | S5 收尾即写一个最小复现测试验证；退路用 `ainvoke(config={"metadata": ...})` 显式传 |
| `embed_configs` 老数据 `api_key_id` 为空（D2=是时） | 列加为 nullable；老数据视作 `key_id IS NULL` 走兜底归属 `channel='embed'`，新建时强制选 |
| `signed_jwt` 验签密钥泄露 | 沿用 `provider.api_key_encrypted` 同套加密入库；只允许通过密钥管理 UI 创建/轮换 |
| generation 行数膨胀 | 单价表 + 截断 I/O 快照（input ≤ 2KB、output ≤ 4KB）；老 root 行字段不变；后续可加分区/归档策略 |
| 前端 widget 改造期间嵌入坏掉 | 保留旧 widget 路径一周；新 widget 灰度切；后台开关 `behavior.legacy_widget=true` 走老逻辑 |

## 10b. 实际执行进度（截至 2026-05-28 收笔）

**已完成（11.5/16）**

| 块 | 内容 | 实际状态 |
|---|---|---|
| S1 | 迁移 p25_a01 drop conversations + create sessions + 加 end_user_id/api_key_id/session_policy | ✅ alembic head |
| S2 | `Conversation` → `ChatSession`；`conversation.py` → `session.py`；新字段进 ORM | ✅ 后端 import 通 |
| S3 | service/schemas/errors 改名；`user` 入参全链路 → sessions.end_user_id + api_key_id | ✅ |
| S4 | TraceContext dataclass + 双 ContextVar + open/set/reset 三件套 | ✅ |
| S5 | GenerationRecorder（含 cost 算价 + 无 scope 兜底 channel='internal'） | ✅ |
| S6 | LLMFactory.reload_llm_cache 给每个 cache 实例烧 callback | ✅ |
| S7 | AgentRun.complete/stream 的 type='generation' span → 'span'（避免双记） | ✅ |
| S8 | agent.service.invoke / stream_invoke 入口 set TraceContext；root call_log 带 observation_type='trace' + api_key_id + end_user_id | ✅ |
| S9 | /v1/conversations/* → /v1/sessions/*；模块 api/conversation/ → api/sessions/；前端 URL 同步 | ✅ |
| S10 | embed session_policy schemas + 三身份模式（device/external/JWT-HS256）；POST /session 接 CreateSessionRequest body；token 绑 end_user_id；embed invoke 设 TraceContext + call_log 带归属 | ✅ |
| S11 | embed 桥：写 sessions 表 + 落 messages（user+assistant 双向）；新增 5 个端点（GET /sessions / messages、POST /sessions/new / delete / name） | ✅ |
| S13 | 后端 EmbedConfigItem / Create / Update 接 api_key_id + session_policy；前端 TS 类型补 SessionPolicy + DEFAULT_SESSION_POLICY + mergeSessionPolicy；tsc 绿 | **半 ✅**（后端 + 类型完整；form modal UI 加 owner key 选择器 + session_policy 表单留待下次） |

**待续（4.5/16）**

| 块 | 内容 | 备注 |
|---|---|---|
| S12 | embed widget 前端（localStorage / 侧栏 / 续接） | 580 行 TS，单独排期 |
| S13b | EmbedFormModal UI 加 owner key 选择器 + session_policy 字段（4 个 boolean + 1 个 select + 1 个数字） | 类型已就位，缺 UI 渲染 |
| S14 | 后台「应用详情 → 会话」tab（用 /v1/sessions） | 新增 tab + 列表组件 |
| S15 | 测试（pytest + 浏览器 e2e） | 跟 S11/S14 配套 |
| S16 | 文档（嵌入接入指南 + Session 管理 + Observability） | 等 S12-S14 落地 |

**头号架构 win 已达成**：BaseLLM 切面收口（S5-S8）。任何路径从 `LLMFactory.create()` 拿模型调 `.ainvoke()/.astream()` 都会自动落一条 `observation_type='generation'` 的 call_log；无 scope 兜底 channel='internal'，**绝不丢账**。归属字段（app_id / api_key_id / end_user_id / channel / agent_key / session_id）从 TraceContext ContextVar 取，由入口（agent.invoke / stream_invoke / embed.invoke_once / embed.stream_invoke）设置。

**全链路嵌入 e2e 已通**：embed POST /session 接收 device_id/external_user_id/jwt_token 解析终端身份 → token 绑 end_user_id → POST /invoke 桥 sessions 表 + messages 写入 + call_log 带归属 → GET /sessions 按 end_user_id 隔离列历史。

## 10. 完成定义（Done 标准）

- [ ] `conversations` 表删；`sessions` 上线；schema 跑通 alembic upgrade head
- [ ] `messages` / `call_logs` / `embed_configs` 加列完成
- [ ] `Conversation` → `ChatSession` 改名全仓零残留（grep 净空）
- [ ] `/v1/sessions/*` 端点全部 OK，旧 `/v1/conversations/*` 全部废弃
- [ ] `InvokeRequest.user` / OpenAI body `user` 全链路透到 `sessions.end_user_id`
- [ ] BaseLLM 工厂注入 GenerationRecorder；任意 `resolve_llm().ainvoke()` 触发 generation 落库
- [ ] AgentRun / Graph 内手记 generation 全部拆完，无双记
- [ ] KB 摄入触发的 LLM 调用能在 call_logs 看到 `channel='internal'` 的 generation 行
- [ ] 嵌入式三种身份模式（anonymous_device / external_user_id / signed_jwt）端到端可用
- [ ] 嵌入 widget 历史侧栏 / 续接 / 新建对话三件全能用
- [ ] 后台「嵌入应用」表单能配 session_policy + 选 owner key
- [ ] 后台「应用详情 → 会话」tab 能查列表 + 过滤 + 删除
- [ ] 浏览器全链路 e2e 跑过；pytest 单元 + 集成测试绿
- [ ] 文档：嵌入接入指南 + Session 管理 + Observability 三篇更新

---

**附：与之前已完成工作的关系**

- `concept-refactor.md`（块 1-4 已完成）：会话账本统一在本计划落地（统一到 `sessions` + `messages` + `call_logs(generation)`）
- `api-key-scope-model.md`：本计划新增 `embed_configs.api_key_id` 对应「key 维度归属」的完善
- v1.1 trace 甘特页（task #28/#47）：本计划补齐 generation 子行后甘特页才有真实嵌套数据

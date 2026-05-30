# 管理员手册

本手册介绍如何使用 Chameleon 管理控制台。

Chameleon 是一站式开源 LLMOps 平台：多源 AI 聚合 + 工作流编排 + RAG 知识库 + Trace/Eval 可观测 + 多 agent 协同 + 可嵌入 SDK。当前为**单租户**部署形态（无多租户 / 配额隔离概念）。

## 一、首次登录

1. 启动服务后查看 `backend/logs/initial-admin-credentials.txt`（容器外）或容器内 `/app/logs/initial-admin-credentials.txt`，该文件由首次启动的 seed 流程写入并 `chmod 600`
2. 浏览器打开 http://localhost:6006
3. 用 admin 凭据登录，**首次登录强制改密码**

## 二、控制台导航

控制台按 **4 个导航域**组织——顶栏切「域」，左侧二级导航展示当前域的分组与叶子项：

```
工作台 (work)
  └ 应用                    本地 / 外部 / 工作流来源的应用 CRUD + 启停 + Playground 试调
                            （工作流编排在「应用」内进入图编辑器）

知识库 (kb)
  └ 知识库                  Collection + 文档 + 分段 + 检索调试

观测 (observe)
  ├ 仪表盘                  24h 调用量曲线 / Top 应用 / 概览
  ├ 运行记录 / Trace        嵌套 observation 调用树（span + generation）
  ├ 会话                    ChatSession 维度的会话账本
  ├ 会话文件                临时会话文件（ephemeral RAG）
  ├ Playground             控制台内直接试调任意应用
  ├ 成本统计               按模型 / 应用 / 时间聚合 token 与成本
  ├ Datasets / 评测任务    评测数据集 + eval 作业
  └ 审计日志               admin 写操作流水

设置 (settings)
  ├ Providers              上游服务商（Dify / FastGPT / OpenAI 兼容等）
  ├ 模型                   provider 下的模型 (chat / embedding / rerank)
  ├ 插件 / 插件市场        工具插件注册与市场
  ├ Key 管理              API 密钥（作用域 global / app / kb）
  ├ 用户管理               admin 用户管理
  ├ 角色管理               角色 + 权限矩阵
  └ 系统配置               系统设置 + 配置导入导出
```

> 模型聚合与上游路由由**外部 oneapi**承担，控制台只管理 Provider / 模型登记与凭证，不再内置渠道矩阵路由。

## 三、典型工作流

### A. 接入新的 LLM Provider（如 DeepSeek）

1. **设置 → Providers** → 新建
   - code: `deepseek`
   - kind: `openai_compatible`
   - base_url: `https://api.deepseek.com/v1`
   - api_key: `sk-xxx`（自动 AES-256-GCM 加密入库）
2. **Providers** 列表 → 点 **测试连通性** 按钮，等待 ✓
3. **设置 → 模型** → 新建
   - provider 选 `deepseek`
   - code: `deepseek-chat`
   - kind: `chat`
4. 至此 `LLMFactory.create("deepseek-chat")` 即可拿到实例

### B. 注册新的本地应用（@agent）

本地应用是进程内运行的 agent，用 `chameleon-agentkit` 的 `@agent` 装饰器声明（隐式拿模型 / KB / trace，支持多具名模型槽、配置 Schema 自动表单）。

1. 在 `backend/chameleon-agents/<key>/`（参考 `examples/echo`、`examples/rag_qa`、`examples/triage`）写 Python 包，用 `@agent(...)` 装饰 `handle` 函数或 `BaseAgent` 子类
2. 通过 entry-points 注册后重启服务，registry 自动发现并落入 `agents` 表（`source='local'`）
3. **工作台 → 应用** 里即可看到该应用，可改名 / 描述 / 关联模型槽 / 启停

调用见 D。本地应用无需在 UI 手动建条目——namespace 扫描自动入表。

### C. 接入外部应用（如 Dify / FastGPT）

无需写代码，直接在控制台配置：

1. **设置 → Providers** → 确认已有 `dify`（或 `fastgpt`）provider，base_url 指向你的实例
2. **工作台 → 应用** → 新建
   - source: `dify`（或 `fastgpt` / `coze`）
   - 关联 provider
   - config: `{"app_id": "dify-app-xxx", "api_key": "..."}`

### C2. 把工作流发布为应用

在「应用」内进入图编辑器编排工作流（节点含 LLM / KB / Tool / HTTP / Code 沙箱 / 意图分类 / If-Else / Iteration / Parallel / AgentDebate / HumanInput 等），发布后即作为 `source='graph'` 的应用对外服务其 `published_spec`，调用方式与其它应用一致（Dify Chatflow 套路）。

### D. 创建 API Key 并调用

1. **设置 → Key 管理** → 新建
   - 选作用域 `scope_type`：
     - `global` —— 通吃所有服务（前缀 `chm_`）；调用时需在 body 指定 `agent_key`
     - `app` —— 仅绑定某个应用（前缀 `agent-`），`scope_ref` = agent_key
     - `kb` —— 仅某知识库（前缀 `kbs-`），`scope_ref` = kb_key
   - 明文 token 留存可重复复制（便利取舍）；请妥善保管，泄露即等同泄密
2. 业务方调用统一走**扁平 invoke**（key 即应用身份，Dify 套路）：
   ```
   POST /v1/invoke
   Authorization: Bearer <token>
   Content-Type: application/json
   {
     "agent_key": "customer-bot",   // app 作用域 key 可省略；global key 必传
     "input": "你好",
     "session_id": null,            // 省略 → 新建会话，响应回显新 ID
     "user": "end-user-123",        // 终端用户外部标识（会话归属 / 按用户计费）
     "stream": false                // true → SSE
   }
   ```
   也可用 **OpenAI 兼容端点**（`/v1/chat/completions` 等）对接既有 SDK。

### E. 生成嵌入式对话 Widget

1. **工作台 → 应用** 进入目标应用的嵌入式配置（embed-configs），新建
   - name: 显示名
   - 关联应用（agent）+ API Key
   - allowed_origins: 允许的来源白名单
   - 身份模式 / 会话策略：匿名、external_user_id 透传、或 JWT 签名身份（支撑嵌入式多用户会话隔离）
2. 列表 → **嵌入代码** 按钮
3. 拷贝以下任一形式到业务方网页：
   - JS Widget（推荐，右下角浮动气泡）
   - iframe（嵌入到页面内某个区域）

嵌入端公开 API 在 `/v1/embed/{embed_key}/*`（`config` / `session` / `invoke` / 文件上传等）。

## 四、用户与权限

### 角色

权限 code 格式 `<resource>:<action>`：

| 示例 | 含义 |
|---|---|
| `users:read` | 查看用户列表 |
| `users:write` | 增删改用户 |
| `*:*` | 超级管理员 |
| `agents:*` | 应用模块所有操作 |

内置角色：
- **admin** — `*:*`（首个 admin 用户绑定）
- **viewer** — 只读权限合集
- **developer** — agents / kbs / providers / models 全权 + 只读其他

新建角色：**设置 → 角色管理** → 新建 → 在 **权限分配** 里勾选 checkbox 矩阵。

### 用户

**设置 → 用户管理** → 新建：

- username 全局唯一
- 默认密码 admin 输入；用户首次登录强制改密
- 选关联角色（可多选）

## 五、知识库

1. **知识库** → 新建 Collection
   - 选 Collection 类型（generic / FAQ / Wiki / API，各自有对应 chunker）
   - 选 embedding model（必须 `kind=embedding`）
2. Collection 详情页 → 上传文档（支持 PDF / Markdown / TXT 等；图片走 VLM caption）
3. 系统后台异步切块 + embedding，状态可在 **任务** 模块查看；可做一致性扫描
4. 检索为 **hybrid**：vector + BM25 + RRF 融合 + 元数据字段过滤 + reranker 重排
5. 关联到应用后，invoke 时自动召回 top-k 拼到 system prompt
6. 会话文件支持 **ephemeral RAG**：小文件全文注入，大文件切块向量召回

## 六、可观测（Trace / 会话 / 成本）

可观测体系对齐 LangSmith：**`call_logs` 是唯一 trace 真相源**，trace 树由嵌套 observation（`span` + `generation`）构成；工作流节点把 span 发进同一棵 trace 树；根行做 rollup（model / token / cost）。控制台把 **Trace** 与 **会话** 拆成两个 tab。

### 运行记录 / Trace

每次对外调用都会写 `call_logs`（root observation + 子 observation）：

- request_id / app_id（调用方标签）/ agent_key / api_key_id / session_id
- success / code / duration_ms / token_usage（prompt / completion / total）/ cost_usd
- model_code / channel（api / openai / embed / playground / internal）/ end_user_id
- 嵌套 observation：parent_id 指向父 request_id，observation_type（span / generation / tool / retriever / embedding 等）
- 入参 / 出参快照（可关闭，避免敏感数据）

支持按应用 / 时间 / 是否成功多维过滤，点开看完整调用树。

### 会话

按 ChatSession 维度聚合（含 end_user_id 终端用户身份层），支撑嵌入式 / 多用户场景的会话账本与历史隔离。

### 成本统计

按 model / 应用 / 时间聚合 token 与 `cost_usd`（成本按当时价目算并存死，改价目不溯源）。

### 审计日志

admin 的所有"写"操作都会写 `audit_logs`：用户改了啥、什么时间、IP / UA。合规审计 / 事故定位用。

## 七、配置导入导出

**设置 → 系统配置** 页面：

- **导出**（`/v1/admin/settings/export-json`）：把当前 DB 里的 providers / models / agents / roles / permissions 等导成 zip（仅 admin）
- **导入**（`/v1/admin/settings/import-json`）：上传 zip，按文件覆盖现有配置（危险，需 `confirm=true`，仅在恢复 / 迁移时用）

适用场景：
- 开发环境 → 生产环境 一次性灌配置
- 多环境同步（dev / staging / prod）

## 八、安全建议

- [ ] admin 用户开启二步验证（roadmap）
- [ ] 定期轮换 provider api_key（admin UI 改密文，DB 旧密文立即失效）
- [ ] 定期轮换 / 吊销 API Key（旧 key 失效；注意明文留存意味着 DB 持有可用密钥）
- [ ] 按最小作用域发 Key：能用 `app` / `kb` 作用域就别用 `global`
- [ ] 监控 `call_logs.success=false` 占比
- [ ] 监控 `audit_logs` 中高危操作（角色改 / 用户密码重置）

## 附录：后端架构速览

后端是 10 个 uv-workspace 包，**严格单向分层**（import-linter 强制护栏，2 契约 GREEN）：

```
core ← data ← integrations ← engine ← (providers / api / system / app / agents / agentkit)
```

| 包 | 职责 |
|---|---|
| `chameleon-core` | 纯协议 + 数据结构 + observe 协议（pydantic-only，禁 sqlalchemy / langchain） |
| `chameleon-data` | ORM 模型（SQLAlchemy 2.0 async）+ infra（db / redis / object_store / jwt / auth / crypto / logger）+ utils + 配置加载 |
| `chameleon-integrations` | 厂商 / 外部实现（LLM 工厂 / embedding / pgvector / reranker / docker 沙箱 / langchain 桥 / observe 落库 handler / plugins registry） |
| `chameleon-engine` | 编排（graph 工作流引擎 + 节点 / retrieval 检索管线 / eval / a2a / jobs） |
| `chameleon-providers` | provider 抽象 + local（进程内 BaseAgent）+ dify + fastgpt + graph |
| `chameleon-agents` | 业务级本地应用（含 examples/） |
| `chameleon-agentkit` | 进程内 agent SDK（`@agent` + ctx 隐式拿模型 / KB / trace，配置 Schema → 自动表单，entry-points 发现） |
| `chameleon-api` | 对外 AI 服务 API（invoke / knowledge / session / task）+ OTLP 摄入 |
| `chameleon-system` | 内部 admin 管理 API（即本控制台后端） |
| `chameleon-app` | 薄 FastAPI 启动器（装配 + lifespan + 中间件 + DI 注入） |

对外 API 面：公开 `/v1/{sessions,kb,embed,files,tasks,otel,auth}` + OpenAI 兼容端点；admin `/v1/admin/{agents,api-keys,app-templates,kbs,graphs,models,providers,datasets,eval-jobs,eval-templates,plugins,marketplace,tools,schemas,scores,search,session-files,settings,users,roles,permissions,audit-logs,dashboard,playground,embed-configs}`。

后端默认监听 7009 端口，控制台前端 dev 6006。

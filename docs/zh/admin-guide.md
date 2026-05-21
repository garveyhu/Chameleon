# 管理员手册

本手册介绍如何使用 Chameleon 管理控制台。

## 一、首次登录

1. 启动服务后查看 `docker/containers/data/logs/initial-admin-credentials.txt`（容器外）或容器内 `/app/logs/initial-admin-credentials.txt`
2. 浏览器打开 http://localhost:6006
3. 用 admin 凭据登录，**首次登录强制改密码**

## 二、菜单概览

```
总览
  └ 仪表盘             24h 调用量曲线 / Top agents/apps

AI 能力
  ├ 智能体             Agent CRUD + 启停 + 测试 invoke
  ├ Providers          上游服务商（Dify / FastGPT / OpenAI 兼容）
  ├ 模型               provider 下的模型 (chat / embedding / rerank)
  ├ 知识库             KB + Doc + Chunk
  └ 嵌入式智能体        生成业务网页可嵌入的对话 widget

应用 & 调用
  ├ 应用 & API Key     业务方的 app 标识 + 调用凭证
  ├ 调用日志           每次 agent invoke 的记录（query/filter）
  ├ 用户               admin 用户管理
  └ 角色               角色 + 权限矩阵

系统
  ├ 审计日志           admin 写操作流水
  ├ 系统配置           导入导出 seed JSON
  └ 关于               版本号 / 许可
```

## 三、典型工作流

### A. 接入新的 LLM Provider（如 DeepSeek）

1. **Providers** → 新建
   - code: `deepseek`
   - kind: `openai_compatible`
   - base_url: `https://api.deepseek.com/v1`
   - api_key: `sk-xxx`（自动 AES-256-GCM 加密入库）
2. **Providers** 列表 → 点 **测试连通性** 按钮，等待 ✓
3. **模型** → 新建
   - provider 选 `deepseek`
   - code: `deepseek-chat`
   - kind: `chat`
4. 至此 `LLMFactory.create("deepseek-chat")` 即可拿到实例

### B. 注册新的本地 Agent

本地 agent 需要先在 `backend/chameleon-agents/<key>/` 写 Python 包，重启服务后 namespace 自动扫到 BaseAgent 子类。

然后在 **智能体** → 新建：

- agent_key: 与 Python 包里 `get_metadata().id` 一致
- source: `local`
- enabled: ✓

保存后调 `/v1/agents/<key>/invoke` 即可。

### C. 接入外部 Agent（如 Dify 应用）

无需写代码，直接 admin UI 配置：

1. **Providers** → 已有 `dify` provider（系统默认有），确认 base_url 是你的 Dify 实例
2. **智能体** → 新建
   - agent_key: 自定义（如 `customer-bot`）
   - source: `dify`
   - config: `{"app_id": "dify-app-xxx", "api_key": "dify-api-key-xxx"}`

### D. 创建应用 + API Key

1. **应用 & API Key** → 新建应用
   - app_key: 业务方标识（如 `mobile-app`）
   - scopes: 选权限范围
2. 该应用下 → 新建 API Key → **明文 token 仅一次回显，请立即保存**
3. 业务方调用：
   ```
   POST /v1/agents/customer-bot/invoke
   Authorization: Bearer <token>
   Content-Type: application/json
   { "input": "你好" }
   ```

### E. 生成嵌入式对话 Widget

1. **嵌入式智能体** → 新建
   - name: 显示名
   - 关联 agent + app
   - allowed_origins: `https://example.com\nhttps://app.example.com`（每行一个）
2. 列表 → **嵌入代码** 按钮
3. 拷贝以下任一形式到业务方网页：
   - JS Widget（推荐，右下角浮动气泡）
   - iframe（嵌入到页面内某个区域）

## 四、用户与权限

### 角色

权限 code 格式 `<resource>:<action>`：

| 示例 | 含义 |
|---|---|
| `users:read` | 查看用户列表 |
| `users:write` | 增删改用户 |
| `*:*` | 超级管理员 |
| `agents:*` | agent 模块所有操作 |

内置角色：
- **admin** — `*:*`（首个 admin 用户绑定）
- **viewer** — 只读权限合集
- **developer** — agents / kbs / providers / models 全权 + 只读其他

新建角色：**角色** → 新建 → 在 **权限分配** 里勾选 checkbox 矩阵。

### 用户

**用户** → 新建：

- username 全局唯一
- 默认密码 admin 输入；用户首次登录强制改密
- 选关联角色（可多选）

## 五、知识库

1. **知识库** → 新建 KB
   - 选 embedding model（必须 `kind=embedding`）
2. KB 详情页 → 上传文档（支持 PDF / Markdown / TXT）
3. 系统后台异步切块 + embedding，状态可在 **任务** 模块查看
4. 关联到 agent 后，invoke 时自动召回 top-k 拼到 system prompt

## 六、审计与监控

### 调用日志

每次 `/v1/agents/*/invoke` 都会写一条 `call_logs`：

- request_id / app_id / agent_key
- success / latency_ms / token_usage
- request body / response body（可关闭，避免敏感数据）

支持按 app / agent / 时间 / 是否成功多维过滤。

### 审计日志

admin 的所有"写"操作都会写 `audit_logs`：用户改了啥、什么时间、IP / UA。

合规审计 / 事故定位用。

## 七、配置导入导出

**系统配置** 页面：

- **导出**：把当前 DB 里的 providers / models / agents / roles / permissions 导成 zip
- **导入**：上传 zip，按文件覆盖现有配置（危险，仅在恢复 / 迁移时用）

适用场景：
- 开发环境 → 生产环境 一次性灌配置
- 多环境同步（dev / staging / prod）

## 八、安全建议

- [ ] admin 用户开启二步验证（v0.1 未支持，roadmap）
- [ ] 定期轮换 provider api_key（admin UI 改密文，DB 旧密文立即失效）
- [ ] 定期轮换 app api_key（业务方旧 key 失效）
- [ ] 监控 `call_logs.success=false` 占比
- [ ] 监控 `audit_logs` 中高危操作（角色改 / 用户密码重置）

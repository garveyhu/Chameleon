# Chameleon

> 中文 · [English](./README.en.md)

**Chameleon** 是一个开源的 **LLMOps 一站式平台** —— 多源智能体聚合 + 可视化工作流编排 + RAG 知识库 + LangSmith 式 Trace/Eval 观测 + 多 agent 协同 + 可嵌入 Widget 与 SDK，一个仓库覆盖 Dify + LangFuse 的核心能力栈。

Python 3.12+ · FastAPI · React 19 · PostgreSQL 16 + pgvector · Docker 一键部署

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

---

## ✨ 能力全景

### 编排与智能体
- **多源智能体聚合** — 本地进程内 agent（agentkit SDK）/ Dify / FastGPT / OpenAI 兼容厂商，统一为一套 HTTP API
- **可视化工作流编排** — ReactFlow 节点编辑器：LLM / 知识库 / 工具 / HTTP / Code 沙箱 / Template / 意图分类路由 / 聚合 / Answer / If-Else / 迭代 / 并行 / Agent Debate / Human-in-loop，支持 draft / published 版本与 chatflow / workflow 两种形态
- **工作流即智能体** — 发布后的 graph 作为 `source=graph` 的 agent 走统一调用端点
- **多 agent 协同** — A2A 协议 + budget 闸门 + 递归深度限制
- **Code 沙箱** — Docker 隔离跑 LLM 生成代码（network=none / read-only / cap-drop ALL）
- **插件市场** — 远端 registry + Ed25519 签名验证 + 一键安装

### 知识库（RAG）
- **Collection 类型** — generic / FAQ / Wiki / API，各自一套 chunker
- **Hybrid 检索** — vector + BM25 + RRF 融合 + 元数据过滤 + reranker
- **VLM 图片 caption** — 图片自动生成可检索 caption（URL 引用，不内嵌 base64）
- **一致性扫描** — 孤儿 chunk / 维度不匹配 / 零向量三类检测 + 一键修复
- **元数据字段** — 自定义字段 + 按字段过滤召回
- **会话文件 ephemeral RAG** — 小文件全文注入 / 大文件独立切块向量

### 观测、评估与成本（LangSmith 化）
- **统一 Trace 树** — `call_logs` 为唯一真相源；嵌套 observation（span + generation）；graph 节点发 span 进同一棵树；根行 rollup 补 model / token / cost
- **Session 账本** — `end_user_id` 身份层，嵌入式 / 多用户会话统一归集
- **Eval 算子** — faithfulness / answer_relevance / context_precision / context_recall（本地实现，不引 ragas 包）+ 数据集 A/B
- **OTLP HTTP 摄入** — 外部应用 trace 经 SDK 直落 Chameleon UI

### 接入与开发体验
- **可嵌入 Widget** — 业务网页一行 `<script>` 接对话气泡，Shadow DOM 隔离；支持会话续接 / 文件图片输入 / 引用卡片 / 深度外观自定义
- **Python / TypeScript SDK** — `@trace` / `patch_openai` / `patch_all` 自动埋点，sync + async
- **agentkit** — 进程内写 agent：`@agent` + `ctx` 隐式拿模型 / 知识库 / trace，多具名模型槽，配置 Schema 自动渲染表单
- **DB 驱动配置** — Provider / Model / Agent / 知识库从后台改，无需重启

---

## 🏗 分层架构

后端是 **uv workspace 多包 monorepo**，按 LangChain 纪律严格分层，由 **import-linter 机器强制单向依赖**（两条契约常绿）：

```
core ← data ← integrations ← engine ← (providers / api / system / app / agents / agentkit)
```

| 层 | 包 | 职责 |
|----|----|------|
| 协议 | `chameleon-core` | 纯协议 + 数据结构 + observe 上下文。pydantic-only，**禁 sqlalchemy / langchain** |
| 持久化 | `chameleon-data` | ORM 模型（SQLAlchemy 2.0 async）+ 基建（db / redis / 对象存储 / jwt / 加密 / 日志）+ 配置 |
| 实现 | `chameleon-integrations` | 厂商实现：LLM 工厂 / embedding / pgvector / reranker / sandbox / langchain 桥 / 观测落库 / 插件 |
| 编排 | `chameleon-engine` | graph 工作流引擎 + 节点 / 检索管线 / 评测 / a2a / jobs |
| 上层 | `chameleon-providers` · `-api` · `-system` · `-app` · `-agents` · `-agentkit` | provider 抽象 / 对外 API / admin API / 启动器 / 业务 agent / agent SDK |

`chameleon-core` 是 pydantic-only 的纯抽象薄壳，所有重 SDK（sqlalchemy / langchain / pgvector / docker）全部下沉到上层 —— 仿 `langchain-core` 的「核心只放抽象」。

---

## 🚀 快速开始

```bash
git clone https://github.com/garveyhu/Chameleon.git
cd Chameleon

# 1. 配置运行时密钥（首次必改）
cp docker/containers/.env.example docker/containers/.env
vim docker/containers/.env
#   PG_PASSWORD / REDIS_PASSWORD / CHAMELEON_JWT_SECRET / CHAMELEON_CRYPTO_KEY

# 2. 一行启动
./docker/scripts/run-local.sh

# 3. 打开 http://localhost:6006
#    首次 admin 凭据：docker/containers/data/logs/initial-admin-credentials.txt
```

详细部署：[docs/zh/deployment.md](./docs/zh/deployment.md) · [English](./docs/en/deployment.md)

---

## 📚 SDK Quickstart

### Python

```bash
pip install chameleon-sdk
```

```python
from chameleon_sdk import Client

client = Client(api_key="sk-...", base_url="http://localhost:7009")

with client.trace(name="my-pipeline") as trace:
    with trace.span("retrieve", observation_type="retriever") as sp:
        sp.set_attribute("kb_id", "smoke")
    with trace.span("llm", observation_type="generation") as sp:
        sp.set_model("gpt-4o-mini")
        sp.set_usage(prompt_tokens=200, completion_tokens=100)

client.flush()
```

详见 [docs/sdk/python.md](./docs/sdk/python.md)。

### TypeScript

```bash
npm install @chameleon/sdk
```

```typescript
import { ChameleonClient } from '@chameleon/sdk';

const client = new ChameleonClient({ apiKey: 'sk-...' });

await client.withTrace('my-pipeline', async (trace) => {
  await trace.withSpan('llm', { observationType: 'generation' }, async (sp) => {
    sp.setModel('gpt-4o-mini');
    sp.setUsage({ promptTokens: 200, completionTokens: 100 });
  });
});

await client.flush();
```

详见 [docs/sdk/typescript.md](./docs/sdk/typescript.md)。

---

## 📦 项目结构

```
Chameleon/
├── backend/                   # FastAPI 后端（uv workspace 多包，import-linter 强制分层）
│   ├── chameleon-core/        # 纯协议 + 数据结构 + observe 上下文（pydantic-only）
│   ├── chameleon-data/        # ORM 模型 + 基建（db/redis/对象存储/jwt/加密/日志）+ 配置
│   ├── chameleon-integrations/# 厂商实现：LLM/embedding/pgvector/reranker/sandbox/桥/观测/插件
│   ├── chameleon-engine/      # 编排：graph 引擎+节点 / 检索 / 评测 / a2a / jobs
│   ├── chameleon-providers/   # provider 抽象 + local/dify/fastgpt/graph
│   ├── chameleon-agents/      # 业务级本地 agent
│   ├── chameleon-agentkit/    # 进程内 agent SDK（@agent + ctx）
│   ├── chameleon-api/         # 对外 AI API（agent/knowledge/session/task）+ OTLP 摄入
│   ├── chameleon-system/      # admin 管理 API
│   └── chameleon-app/         # FastAPI 启动器（装配 + lifespan + DI 注入）
├── frontend/                  # React 19 控制台（4 域：工作台 / 知识库 / 观测 / 设置）
│   ├── src/core/              # 共享基建（lib / components / stores / router）
│   ├── src/system/<module>/   # 业务模块（pages / services / types 自包含）
│   └── embed/                 # 可嵌入 Widget（独立 Vite 工程）
├── sdk/{python,typescript}/   # chameleon-sdk / @chameleon/sdk
├── docker/                    # 三区（images / containers / scripts）
└── docs/                      # 中英双语 + ADR + SDK
```

## 🛠 技术栈

**后端**：Python 3.12 + uv · FastAPI · SQLAlchemy 2.0 async · PostgreSQL 16 + pgvector · Redis · MinIO · loguru · pytest · ruff · **import-linter（分层护栏）** · APScheduler · docker-py · PyNaCl

**前端**：React 19 · TypeScript strict · Vite · Tailwind v4 + Radix UI · TanStack Query · Zustand · ReactFlow

**SDK**：Python httpx async/sync · TypeScript Node 18+ / browser · OTLP HTTP

**部署**：Docker + Compose · 多阶段镜像 · BuildKit 多架构

## 📚 文档

| 主题 | 路径 |
|---|---|
| 架构设计 | [docs/architecture.md](./docs/architecture.md) |
| 上手指南 | [docs/getting-started.md](./docs/getting-started.md) |
| 部署指南 | [docs/zh/deployment.md](./docs/zh/deployment.md) |
| API 参考 | [docs/api-reference.md](./docs/api-reference.md) |
| Provider 接入 | [docs/providers.md](./docs/providers.md) |
| 扩展开发 | [docs/extension-guide.md](./docs/extension-guide.md) |
| 嵌入接入 | [docs/embed-integration-guide.md](./docs/embed-integration-guide.md) |
| Python / TS SDK | [docs/sdk/python.md](./docs/sdk/python.md) · [docs/sdk/typescript.md](./docs/sdk/typescript.md) |
| 决策记录（ADR） | [docs/adr/](./docs/adr/) |

## 🤝 贡献

PR 欢迎。Commit 遵循 Angular 规范（见 git history）。

## 📄 License

[MIT](./LICENSE)

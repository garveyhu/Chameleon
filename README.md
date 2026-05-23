# Chameleon

> 中文 · [English](./README.en.md)

**Chameleon** 是一个开源的 **LLMops 一站式平台** —— 多源 AI 聚合 + 工作流编排 + RAG 知识库 + Trace/Eval 观测 + 多 agent 协同 + SaaS 化 SDK，一个仓库覆盖 Dify + LangFuse + One-API 的能力栈。

**v1.0.0** · Python 3.12+ · FastAPI · React 19 · PostgreSQL 16 + pgvector · OpenTelemetry · Docker 一键部署

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

---

## ✨ v1.0 能力全景

### 网关与编排
- **多源 Agent 聚合** — local LangGraph / Dify / FastGPT / OpenAI 兼容厂商统一为一套 HTTP API
- **工作流编排** — 节点级 graph 编辑器（LLM / KB / Tool / If-Else / Agent Debate），支持 **draft / published 版本**
- **Sandbox 工具运行** — Docker 隔离跑 LLM 生成的代码（network=none / read-only / nobody / cap-drop ALL）
- **Plugin Marketplace** — 远端 registry + Ed25519 签名验证 + 一键安装

### 观测、评估与成本
- **完整 Trace 树** — `parent_id` 嵌套 observation；call_logs → 11 维 audit + spans
- **Cost dashboard** — 按 model 价目计算（可重放）+ 多维聚合（user/agent/model/channel）
- **EvalTemplate + RAGAS 4 算子** — faithfulness / answer_relevance / context_precision / context_recall（本地实现，不引 ragas 包）
- **OTLP HTTP 摄入** — `chameleon.patch_all()` 让外部应用 trace 直落 Chameleon UI

### 知识库与对话
- **KB Collection 类型** — generic / FAQ / Wiki / API 各自一套 chunker
- **Hybrid 6 步检索** — vector + BM25 + dedupe + RRF + filter + reranker
- **VLM 图片 caption** — 图片自动生成可检索 caption（URL 引用，不内嵌 base64）
- **KB 一致性扫描** — 孤儿 chunk / dim mismatch / zero vector 三类检测 + 半软删 + 一键修复
- **Dataset PII 脱敏** — 从 call_log 一键采样到 dataset，mask / drop / keep 三策略
- **对话树 + 分支** — `parent_message_id` 树形 + regenerate / edit-and-resend

### Multi-tenant 与企业级
- **RBAC 三表** — users / roles / permissions
- **Workspace + 配额** — 月度 reset cron + token / request 双闸门
- **审计 11 维** — actor / workspace / session / action / resource / before / after / ip / ua / request_id / created_at
- **AES-256-GCM** — provider 凭证加密存储

### SDK 与开发体验
- **Python SDK** — `pip install chameleon-sdk`；sync + async 双形态；`@trace` / `patch_openai` / `patch_all`
- **TypeScript SDK** — `npm install @chameleon/sdk`；Node 18+ & browser
- **可嵌入 Widget** — 业务网页一行 `<script>` 接对话气泡；shadow DOM 隔离
- **Multi-agent debate 节点** — A2A 协议 + budget + 状态机
- **应用市场 templates** — assistant / agent / workflow / rag 四类公共模板，一键克隆
- **移动端响应式** — sidebar 自动 collapsed / playground 移动端单列 / widget fullscreen

---

## 🚀 快速开始

```bash
git clone https://github.com/garveyhu/Chameleon.git
cd Chameleon

# 1. 配置运行时密钥（**首次必改**）
cp docker/containers/.env.example docker/containers/.env
vim docker/containers/.env
#   PG_PASSWORD / REDIS_PASSWORD / CHAMELEON_JWT_SECRET / CHAMELEON_CRYPTO_KEY

# 2. 一行启动
./docker/scripts/run-local.sh

# 3. 打开 http://localhost:6006
#    首次 admin 凭据：docker/containers/data/logs/initial-admin-credentials.txt
```

详细部署文档：[docs/zh/deployment.md](./docs/zh/deployment.md) · [English](./docs/en/deployment.md)

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

## 🆚 对标

| 主题 | Dify | LangFuse | One-API | **Chameleon v1.0** |
|---|---|---|---|---|
| 多模型聚合 | ✓ | ✗ | ✓ | ✓（含 channel matrix 路由） |
| 工作流编排 | ✓ | ✗ | ✗ | ✓（含 draft/published 版本） |
| RAG 知识库 | ✓ | ✗ | ✗ | ✓（hybrid 6 步 + 4 类 chunker） |
| Trace / Eval | partial | ✓ | ✗ | ✓（含 RAGAS 4 算子 + OTLP） |
| Plugin 生态 | ✓ | ✗ | ✗ | ✓（manifest Ed25519 + marketplace） |
| Multi-agent | partial | ✗ | ✗ | ✓（A2A + debate 状态机） |
| SaaS SDK | partial | ✓ | ✗ | ✓（Python + TS auto-patch） |
| Multi-tenant 配额 | partial | partial | ✗ | ✓（workspace + 月度 reset） |

---

## 📦 项目结构

```
chameleon/
├── backend/                  # FastAPI 后端（uv workspace 多包）
│   ├── chameleon-core/       # 基础设施：DB / Redis / JWT / 加密 / ORM /
│   │                         # retrieval / eval / sandbox / agent / observe
│   ├── chameleon-providers/  # Provider 抽象层
│   ├── chameleon-agents/     # 业务级本地 agent
│   ├── chameleon-api/        # 对外 AI 业务 API（含 OTLP 摄入）
│   ├── chameleon-system/     # admin 管理 API
│   └── chameleon-app/        # FastAPI 启动器
├── frontend/                 # React 19 管理控制台
│   └── src/system/<module>/  # 业务模块（pages / services / types / routes 自包含）
├── sdk/
│   ├── python/               # chameleon-sdk Python 包
│   └── typescript/           # @chameleon/sdk TS 包
├── docker/                   # 三区结构（images / containers / scripts）
└── docs/                     # 中英双语 + ADR + SDK + release notes
```

## 🛠 技术栈

**后端**：Python 3.12 + uv · FastAPI · SQLAlchemy 2.0 async · PostgreSQL 16 + pgvector · Redis · loguru · pytest · ruff · APScheduler · docker-py · PyNaCl

**前端**：React 19 · TypeScript strict · Vite · Tailwind v4 + Radix UI · TanStack Query · Zustand · react-i18next · ReactFlow

**SDK**：Python httpx async/sync · TypeScript Node 18+ / browser fetch · OTLP HTTP

**部署**：Docker + Compose · 多阶段镜像 · BuildKit 多架构

## 📚 文档

| 主题 | 路径 |
|---|---|
| 部署指南 | [docs/zh/deployment.md](./docs/zh/deployment.md) |
| 架构设计 | [docs/zh/architecture.md](./docs/zh/architecture.md) |
| Python SDK | [docs/sdk/python.md](./docs/sdk/python.md) |
| TypeScript SDK | [docs/sdk/typescript.md](./docs/sdk/typescript.md) |
| 决策记录（ADR） | [docs/adr/](./docs/adr/) |
| v1.0 升级指南 | [docs/release/v1.0-migration.md](./docs/release/v1.0-migration.md) |
| v1.0 benchmark | [docs/release/v1.0-benchmark.md](./docs/release/v1.0-benchmark.md) |
| 阶段计划归档 | [docs/plans/](./docs/plans/) |

## 🤝 贡献

PR 欢迎！Commit 遵循 Angular 规范（见 git history）。
v1.0 后 public API 进 deprecation policy（保留 1 minor 版本）。

## 📄 License

[MIT](./LICENSE)

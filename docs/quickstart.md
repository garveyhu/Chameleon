# 5 分钟 Quickstart

> 目标：本地起 Chameleon → 登录 admin → 配置 Provider + Model → 建一个 RAG 知识库 → 上传文档 → Playground 命中 → 看 Trace

## 1. 环境

需要：Docker + Docker Compose（macOS / Linux 都行）。

## 2. 启动

```bash
git clone https://github.com/garveyhu/Chameleon.git
cd Chameleon

cp docker/containers/.env.example docker/containers/.env
# 编辑 .env 改敏感值：PG_PASSWORD / REDIS_PASSWORD / CHAMELEON_JWT_SECRET / CHAMELEON_CRYPTO_KEY
vim docker/containers/.env

./docker/scripts/run-local.sh
```

几分钟后访问 http://localhost:6006（后端 API 在 http://localhost:7009/docs）。

首次启动会自动 seed admin，登录凭据写在：
`docker/containers/data/logs/initial-admin-credentials.txt`

## 3. 配置 Provider + Model

模型聚合/路由由外部 oneapi 等网关承担，Chameleon 侧只需登记「从哪个 base_url 用哪个 key 调哪个模型」。登录后进入 **设置** 域：

1. **设置 → Providers**：确认内置 provider 已注册，或新建一条 provider
   - kind：`llm`（也支持 `embedding` / `dify` / `fastgpt` / `coze`）
   - base_url：`https://dashscope.aliyuncs.com/compatible-mode/v1`（通义千问 OpenAI 兼容示例）
   - api_key：你的 key（AES-256-GCM 加密落库）
2. **设置 → 模型**：新建一个 model
   - 关联上一步的 provider
   - kind：`chat`
   - code：`qwen-plus`

embedding 模型同理：建一个 kind=`embedding` 的 model（如 `text-embedding-v3`），供知识库使用。

## 4. 建 RAG 知识库

进入 **知识库** 域：

1. **知识库 → 新建**：填 name=`demo`，选 embedding model（如 `text-embedding-v3`）
2. 详情页 → 文档 → 拖一个 markdown / pdf 上传
3. 等切块 / 嵌入完成（status → ready）
4. 详情页 → 检索测试 → 输入 query，验证 hybrid 检索（vector + BM25 + RRF + reranker）命中

## 5. Playground 跑 chat

进入 **观测** 域：

1. **观测 → Playground**
2. 选 model（`qwen-plus`）+ 选知识库（`demo`）
3. 输入问题，看到回答 + KB 引用

## 6. 看 Trace

call_logs 是唯一的 trace 真相源，每次调用都落成嵌套 observation（span + generation）的 trace 树。

1. **观测 → 运行记录 / Trace**
2. 点一条记录进详情页：左侧 trace tree，右侧看 Request / Response payload、model / token / cost
3. **观测 → 会话** 可按 Session 维度回看多轮对话

## 7. 装 SDK（可选）

Python：

```bash
pip install chameleon-sdk
```

```python
from chameleon_sdk import Client, patch_openai

client = Client(api_key="<your-app-key>", base_url="http://localhost:7009")
patch_openai(client)  # 之后 openai 调用自动 trace

import openai
openai.OpenAI().chat.completions.create(
    model="qwen-plus",
    messages=[{"role": "user", "content": "hi"}],
)
client.flush()
```

回 admin → **观测 → 运行记录 / Trace** 看到刚才的 openai 调用 ✓

## 下一步

- [架构设计](./zh/architecture.md)
- [Python SDK 完整文档](./sdk/python.md)
- [TypeScript SDK 完整文档](./sdk/typescript.md)
- [v1.0 升级指南](./release/v1.0-migration.md)

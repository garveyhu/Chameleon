# 5 分钟 Quickstart

> 目标：本地起 Chameleon → 注册账号 → 建一个 RAG agent → 上传文档 → chat 命中

## 1. 环境

需要：Docker + Docker Compose（macOS / Linux 都行）。

## 2. 启动

```bash
git clone https://github.com/garveyhu/Chameleon.git
cd Chameleon

cp docker/containers/.env.example docker/containers/.env
# 编辑 .env 改 4 个密钥（任意强密码即可）
vim docker/containers/.env

./docker/scripts/run-local.sh
```

3 分钟后访问 http://localhost:6006，首次 admin 凭据在：
`docker/containers/data/logs/initial-admin-credentials.txt`

## 3. 配置 Model + Channel

1. 登录 admin → AI 配置 → Providers，确认 `local` / `openai-compat` provider 已注册
2. AI 配置 → Channels，加一条 channel：
   - base_url：`https://dashscope.aliyuncs.com/compatible-mode/v1`（通义千问示例）
   - api_key：你的 key
3. AI 配置 → Models，加 `qwen-plus`，关联 channel
4. AI 配置 → Agents，新建 `local` source agent，关联默认 model

## 4. 建 RAG KB

1. AI 配置 → 知识库 → 新建：name=demo，embedding_model=text-embedding-3-small
2. 详情页 → 文档 → 拖一个 markdown / pdf
3. 等切块 / 嵌入完成（status → ready）
4. 详情页 → 检索测试 → 输入 query 验证

## 5. Playground 跑 chat

1. AI 配置 → Playground
2. 选 agent + 选 KB
3. 输入问题，看到回答 + KB 引用

## 6. 看 Trace

1. 访问控制 → 调用日志 → 点行展开
2. 看 5 个 tab：trace tree / request / response / timeline / scores

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

回 admin / Trace 树看到刚才的 openai 调用 ✓

## 下一步

- [架构设计](./zh/architecture.md)
- [Python SDK 完整文档](./sdk/python.md)
- [TypeScript SDK 完整文档](./sdk/typescript.md)
- [v1.0 升级指南](./release/v1.0-migration.md)

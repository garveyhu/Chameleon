# 贡献指南 · Contributing to Chameleon

Chameleon 是一个**以代码为核心的智能体编排框架**：作者只写业务逻辑（`@agent` +
`async def handle(ctx)`），平台隐式提供模型池 / 知识库 / 向量 / 会话 / 追踪 / 计费 /
工具 / 子智能体 / 嵌入式分发。欢迎贡献。

## 仓库结构

```
backend/                  uv workspace 多包（Python 3.12+ / FastAPI / SQLAlchemy）
  chameleon-core/         纯协议 + 数据结构（仿 langchain-core）
  chameleon-data/         ORM models + 基础设施（db / redis / minio / jwt）
  chameleon-integrations/ 厂商实现（LLM / embedding / 向量 / 工具 / 沙箱 / 媒体生成）
  chameleon-engine/       编排（graph 引擎 / 检索管道 / 评测 / a2a）
  chameleon-agentkit/     ⭐ 智能体作者 SDK（@agent / ctx）—— 对外冻结公共面
  chameleon-agents/       业务 / 示例 agent（每个一个文件夹）
  chameleon-providers/    provider（local / graph / dify / fastgpt / comfyui）
  chameleon-api · -system · -app   HTTP 路由 / 业务服务 / app 入口
frontend/                 React + Vite + TS（yarn）
docs/plans/               设计方案 SSOT
```

依赖铁律：`core ← data ← integrations ← aikit ← engine ← 上层`，单向不可反向
（`uv run lint-imports` 守门，**3 契约必须 GREEN**）：
1. core 保持纯抽象（禁 sqlalchemy / langchain 系）；
2. 分层基座单向（禁反向 / 越层）；
3. agentkit 公共 SDK 精简（禁依赖 data / 重 ORM —— 保 `pip install chameleon-agentkit`
   只拉 core + mcp，不被动拖 sqlalchemy/fastapi）。

## 本地起环境

```bash
cd backend && ./run.sh            # dev：127.0.0.1:7009，热更新，自动迁移
cd frontend && yarn dev           # 127.0.0.1:6006
```

## 写一个智能体（零样板）

把一个文件夹丢进 `backend/chameleon-agents/`，重启即注册运行 —— **无需改任何 app
配置、无需声明依赖**（dev 态由 `CHAMELEON_AGENTS_ROOT` 命名空间自动发现）：

```
chameleon-agents/my-bot/src/chameleon/agents/my_bot/agent.py
```

```python
from chameleon.agentkit import agent, AgentRun, ModelSlot, tool

@tool(name="calc", description="算术")
async def calc(expression: str) -> dict:
    return {"value": eval(expression, {"__builtins__": {}}, {})}

@agent(key="my-bot", name="我的助手", models=[ModelSlot("chat", "对话模型")], kb=True)
async def handle(ctx: AgentRun):
    docs = await ctx.kb.search(ctx.query, mode="hybrid")        # 知识库（自动引用）
    async for d in ctx.run_with_tools(                          # 工具循环（ReAct）
        slot="chat", system="你是助手", user=ctx.query, tools=[calc],
    ):
        yield d
```

ctx 能力面见 `backend/chameleon-agentkit/README.md`。本地自测三态（同一份 handle）：
- **脱平台**（最低摩擦，不连任何站点）：`pip install chameleon-agentkit` + 自带 LangChain
  模型 → `StandaloneTransport` + `run_standalone`（见 `chameleon-agentkit/examples/`）。
- **dev 服务**：`agentkit lint/run/chat <module>`（需 `CHAMELEON_DEV_TOKEN`，经 dev 端点用站内资源）。
- **站内**：提交后 `InProcessTransport` 进程内跑。
脱平台 vs 平台的行为差异（kb/trace/工具事件等）见 `docs/agentkit-guide.md`「完全脱平台跑」。

## 提交规范

- Commit message 走 **Angular 规范**：`<type>(<scope>): <subject>`（type 用英文，
  subject 可中文）。type ∈ feat/fix/docs/style/refactor/perf/test/build/ci/chore/revert。
- 提交前：`ruff`（后端）+ `tsc` + `eslint`（前端）+ 相关单测 + `lint-imports` 必须过。
- CI（`.github/workflows/agentkit-ci.yml`）自动跑：ruff + import-linter 三契约 + 离线鲁棒性
  套件（agentkit/沙箱/并发/重试，无需 DB/真 LLM）。真 LLM e2e（`scripts/e2e_real_agents.py`）
  需起平台 + 真模型 + token，是独立手跑/带服务门，不在该 workflow。
- 改了 UI 必须起浏览器肉眼核实再提交。
- agentkit 公共面（`chameleon.agentkit.__all__`）**只增不改**，破坏性变更走 major 版本。

## 测试

```bash
cd backend && .venv/bin/python -m pytest <path>          # 后端
cd frontend && yarn test:run                              # 前端
```

- agentkit 离线单测：`chameleon.agentkit.testing.FakeTransport`（可编程模型/kb/工具，确定性，
  无需服务），见 `chameleon-agentkit/tests/`。
- 真客户端 e2e（零 API 花费）：`respx` 拦 httpx 让真 `langchain_openai.ChatOpenAI` 跑 canned
  响应，演练真实 SDK 集成（见 `test_standalone_real_client_e2e.py`，覆盖 complete/stream/gather/工具）。
- 真 LLM 端到端验证门（需起平台 + 真模型 + dev token）：`scripts/e2e_real_agents.py`——经
  `/v1/dev/call_agent` 用真模型实跑八项（对话/工具/A2A/RAG/多模型/MCP/结构化/路由）并断言，任一失败退非 0。
- 集成测试不 mock 数据库（用 test 库）；并发/子进程测试加硬超时看门狗。
- 注：全套件存在一批 pre-existing 失败（跨测试状态污染 / event-loop 级联），新增改动不应
  引入**新**失败。

## 行为准则

参与本项目即同意遵守友善、专业、包容的协作准则（CODE_OF_CONDUCT，待补）。

## License

> ⚠️ 开源协议待项目维护者确认（推荐 Apache-2.0）。LICENSE 文件确定后补充。

"""example-classic —— BaseAgent 类式写法（高级 / 有状态用法）。

展示类式 @agent：装饰一个 BaseAgent 子类，定义实例方法 `handle(self, run)`。与函数式
**共用同一 AgentRun ctx**——同样能用 run.complete / run.stream / run.kb / run.tools /
run.memory / run.call_agent。适合需要持有实例状态、拆多方法的复杂 agent。

同时演示 `sandboxed=True` 标志（接口预留：声明该 agent 期望隔离执行；真正容器隔离
按部署需求启用，当前进程内运行）。
"""

from __future__ import annotations

from chameleon.agentkit import AgentRun, BaseAgent, ModelSlot, agent


@agent(
    key="example-classic",
    name="经典类式",
    description="BaseAgent 类式写法（共享同一 ctx）",
    tags=["example", "class"],
    models=[ModelSlot("chat", "对话模型")],
    sandboxed=True,
)
class ClassicAgent(BaseAgent):
    # 无需手写 get_metadata —— @agent 从声明自动合成（单一真相源，T3-5）。

    async def handle(self, run: AgentRun):
        async for delta in run.stream(
            slot="chat",
            system="你是助手，用简洁中文作答。",
            user=run.query,
        ):
            yield delta

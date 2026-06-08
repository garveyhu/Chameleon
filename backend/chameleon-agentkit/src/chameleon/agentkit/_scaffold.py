"""`agentkit new` 脚手架 —— 一条命令生成可直接跑的 @agent 包骨架。

把「建文件夹 + 只写业务逻辑」的愿景变成一条命令：生成 workspace 成员包（pyproject +
entry-point + 最小 @agent handler 样板），丢进 chameleon-agents/ 即被自动发现（T3-1）。
"""

from __future__ import annotations

import re
from pathlib import Path


def _slug(name: str) -> tuple[str, str]:
    """规整出 (agent_key kebab, package snake)。"""
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not base:
        raise ValueError("agent 名非法：需含字母/数字")
    key = base
    pkg = base.replace("-", "_")
    return key, pkg


def _agent_py(key: str) -> str:
    return f'''"""{key} —— @agent 业务逻辑（平台提供模型/KB/工具/记忆/多模态/trace）。"""

from __future__ import annotations

from chameleon.agentkit import AgentRun, ModelSlot, agent


@agent(
    key="{key}",
    name="{key}",
    description="TODO 一句话描述这个智能体",
    tags=["custom"],
    models=[ModelSlot("chat", "对话模型")],
    # kb=True,                       # 需要知识库检索就打开，handler 里用 ctx.kb.search()
    # tools=["http"],                # 需要平台工具（http/sql/...）就声明
)
async def handle(ctx: AgentRun):
    # 只写业务逻辑：模型/KB/工具/记忆/多模态/trace 都从 ctx 隐式拿
    async for delta in ctx.stream(
        slot="chat",
        system="你是一个有帮助的助手。",
        user=ctx.query,
    ):
        yield delta

    # 进阶（按需取消注释）：
    #   docs = await ctx.kb.search(ctx.query, mode="hybrid")        # 检索增强
    #   async for d in ctx.run_with_tools(slot="chat", user=ctx.query, tools=[...]): ...  # 工具循环
    #   pref = await ctx.memory.get("pref")                          # 跨会话记忆
    #   img = await ctx.media.generate(kind="image", prompt="...")  # 多模态生成
'''


def _init_py(key: str, pkg: str) -> str:
    return f'''"""{key}: @agent 业务包。"""

from chameleon.agents.{pkg}.agent import handle

__all__ = ["handle"]
'''


def _pyproject(key: str, pkg: str) -> str:
    return f'''[project]
name = "chameleon-agent-{key}"
version = "0.1.0"
description = "Chameleon 智能体：{key}"
requires-python = ">=3.12"
dependencies = ["chameleon-agentkit"]

[tool.uv.sources]
chameleon-agentkit = {{ workspace = true }}

[project.entry-points."chameleon.agents"]
{key} = "chameleon.agents.{pkg}"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/chameleon"]
'''


def render_files(name: str) -> dict[str, str]:
    """生成 {相对路径: 内容}（纯函数，可单测）。"""
    key, pkg = _slug(name)
    base = f"{key}/src/chameleon/agents/{pkg}"
    return {
        f"{key}/pyproject.toml": _pyproject(key, pkg),
        f"{base}/__init__.py": _init_py(key, pkg),
        f"{base}/agent.py": _agent_py(key),
    }


def write_scaffold(name: str, dest: str | Path) -> Path:
    """把脚手架写到 dest/<key>/；返回包根目录。已存在则报错（不覆盖）。"""
    key, _ = _slug(name)
    root = Path(dest) / key
    if root.exists():
        raise FileExistsError(f"目标已存在，未覆盖：{root}")
    for rel, content in render_files(name).items():
        path = Path(dest) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root

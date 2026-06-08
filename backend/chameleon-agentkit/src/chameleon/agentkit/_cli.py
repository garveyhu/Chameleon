"""agentkit CLI —— 本地开发自测。

    agentkit new   <name> [-d DIR]            脚手架：生成新 @agent 包骨架
    agentkit lint  <module[:attr]>            校验 @agent 声明
    agentkit run   <module[:attr]> -i "..."   单次跑一句
    agentkit chat  <module[:attr]>            交互式 REPL

作者代码不变：ctx 的模型 / KB / 工具经 HttpDevTransport 回调站内 dev 服务
（同一份代码提交后走 InProcessTransport 进程内跑）。

环境变量：
    CHAMELEON_DEV_URL    dev 服务地址（默认 http://localhost:7009）
    CHAMELEON_DEV_TOKEN  dev token（须与服务端 .env 的 CHAMELEON_DEV_TOKEN 一致）
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import os
import sys
from typing import Any

from chameleon.agentkit._decorator import declared_agents
from chameleon.agentkit._runtime import AgentRun
from chameleon.agentkit._spec import AgentManifest

_DIM = "\033[2m"
_CYAN = "\033[36m"
_RESET = "\033[0m"


def _load_manifest(target: str) -> AgentManifest:
    """import 作者模块，定位被 @agent 装饰的对象，返回其 manifest。"""
    mod_path, _, attr = target.partition(":")
    mod = importlib.import_module(mod_path)
    if attr:
        obj = getattr(mod, attr)
        man = getattr(obj, "__agent_manifest__", None)
        if man is None:
            raise SystemExit(f"{target} 不是 @agent 声明的对象")
        return man
    # 未指定 attr：取本次 import 触发登记、且定义在该模块里的 @agent
    found = [
        m
        for m in declared_agents().values()
        if getattr(m.handler, "__module__", "").startswith(mod_path)
    ]
    if not found:
        raise SystemExit(f"模块 {mod_path} 未发现 @agent 声明")
    if len(found) > 1:
        keys = ", ".join(m.key for m in found)
        raise SystemExit(f"模块 {mod_path} 有多个 @agent，请用 module:attr 指定（{keys}）")
    return found[0]


def _default_config(man: AgentManifest) -> dict[str, Any]:
    return {o.key: o.default for o in man.config if o.default is not None}


def _build_run(man: AgentManifest, query: str, history: list[Any]) -> tuple[AgentRun, Any]:
    from chameleon.agentkit._dev_transport import HttpDevTransport

    base = os.environ.get("CHAMELEON_DEV_URL", "http://localhost:7009")
    token = os.environ.get("CHAMELEON_DEV_TOKEN", "")
    if not token:
        raise SystemExit("缺少 CHAMELEON_DEV_TOKEN 环境变量（须与服务端 .env 一致）")
    from dataclasses import asdict

    transport = HttpDevTransport(
        base_url=base,
        token=token,
        agent_key=man.key,
        platform_tool_keys=man.tools,
        # @agent(mcp_servers=) 本地直连：带 MCP 的 agent 也能本地自测（与站内一致）
        mcp_servers=[asdict(s) for s in (man.mcp_servers or [])],
    )
    run = AgentRun(
        transport=transport,
        agent_key=man.key,
        query=query,
        messages=[],
        history=history,
        session_id=None,
        config=_default_config(man),
    )
    return run, transport


async def _invoke(man: AgentManifest, query: str, history: list[Any]) -> str:
    run, transport = _build_run(man, query, history)
    handler = man.handler
    pieces: list[str] = []

    def _flush_events() -> None:
        for ev in transport.drain():
            etype = ev.get("type") if isinstance(ev, dict) else getattr(ev, "type", "")
            data = ev.get("data") if isinstance(ev, dict) else getattr(ev, "data", {})
            if etype == "tool_call":
                print(f"{_DIM}  ⟳ tool_call {data.get('name')}({data.get('args')}){_RESET}")
            elif etype == "tool_result":
                print(f"{_DIM}  ✓ tool_result {data.get('name')} → {data.get('result')}{_RESET}")
            elif etype == "citation":
                print(f"{_DIM}  ◦ citation {data.get('source')}{_RESET}")

    result = handler(run)
    if inspect.isasyncgen(result):
        async for chunk in result:
            _flush_events()
            sys.stdout.write(chunk)
            sys.stdout.flush()
            pieces.append(chunk)
        _flush_events()
        print()
    else:
        text = await result
        _flush_events()
        print(text)
        pieces.append(text or "")
    _render_trace(transport)
    return "".join(pieces)


def _render_trace(transport: Any) -> None:
    """打印本轮 dev trace 树（span 名 + 耗时 + 嵌套）—— 本地可观测，替代 NullSpan。"""
    spans = transport.drain_spans() if hasattr(transport, "drain_spans") else []
    if not spans:
        return
    # span 按退出顺序记录（内层先）→ reverse 得外层在前，depth 缩进成树
    print(f"{_DIM}  ── trace ──{_RESET}")
    for s in reversed(spans):
        indent = "  " * (s.get("depth", 0) + 1)
        mark = "✗" if s.get("error") else "·"
        name = s.get("name", "span")
        dur = s.get("duration_ms", 0)
        print(f"{_DIM}  {indent}{mark} {name} {dur}ms{_RESET}")


def _cmd_lint(target: str) -> int:
    man = _load_manifest(target)
    print(f"{_CYAN}✓ @agent{_RESET} key={man.key} name={man.name}")
    print(f"  models : {[s.name for s in man.models] or '—'}")
    print(f"  tools  : {man.tools or '—'}")
    print(f"  config : {[o.key for o in man.config] or '—'}")
    print(f"  kb     : {man.kb}")
    return 0


def _cmd_run(target: str, text: str) -> int:
    man = _load_manifest(target)
    asyncio.run(_invoke(man, text, []))
    return 0


def _cmd_chat(target: str) -> int:
    man = _load_manifest(target)
    print(f"{_CYAN}agentkit chat{_RESET} · {man.name} ({man.key}) · 输入空行 / Ctrl-C 退出")
    history: list[Any] = []
    while True:
        try:
            q = input(f"{_CYAN}你 ›{_RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not q:
            return 0
        asyncio.run(_invoke(man, q, history))
    return 0


def _cmd_new(name: str, dest: str) -> int:
    from chameleon.agentkit._scaffold import write_scaffold

    try:
        root = write_scaffold(name, dest)
    except (FileExistsError, ValueError) as e:
        print(f"✗ {e}")
        return 1
    print(f"{_CYAN}✓ 已生成 @agent 包{_RESET} {root}")
    print(f"  {_DIM}1. 编辑 {root.name}/src/chameleon/agents/*/agent.py 写业务逻辑")
    print("  2. 丢进 backend/chameleon-agents/ 即被自动发现（dev 起服务后）")
    print(f"  3. 本地自测：agentkit chat {root.name.replace('-', '_')}.agent{_RESET}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentkit", description="agentkit 本地开发自测")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("lint", "run", "chat"):
        p = sub.add_parser(name)
        p.add_argument("target", help="作者模块，如 my_pkg.agent 或 my_pkg.agent:handle")
        if name == "run":
            p.add_argument("-i", "--input", required=True, help="单次输入")
    pn = sub.add_parser("new", help="脚手架：生成一个新 @agent 包骨架")
    pn.add_argument("name", help="agent 名（kebab-case，如 weather-bot）")
    pn.add_argument("-d", "--dir", default=".", help="生成目录（默认当前目录）")
    ns = parser.parse_args(argv)
    if ns.cmd == "lint":
        return _cmd_lint(ns.target)
    if ns.cmd == "run":
        return _cmd_run(ns.target, ns.input)
    if ns.cmd == "chat":
        return _cmd_chat(ns.target)
    if ns.cmd == "new":
        return _cmd_new(ns.name, ns.dir)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

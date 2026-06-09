"""agentkit CLI —— 本地开发自测。

    agentkit new   <name> [-d DIR]            脚手架：生成新 @agent 包骨架
    agentkit lint  <module[:attr]>            校验 @agent 声明
    agentkit run   <module[:attr]> -i "..."   单次跑一句
    agentkit chat  <module[:attr]>            交互式 REPL
    agentkit dev   <module[:attr]> -i "..."   watch 源文件，改动即热重载重跑（本地迭代闭环）

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
import time
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


def _module_source(mod_path: str) -> str:
    """该模块的源文件路径（watch 目标）。"""
    mod = sys.modules.get(mod_path) or importlib.import_module(mod_path)
    src = getattr(mod, "__file__", None)
    if not src:
        raise SystemExit(f"无法定位模块源文件：{mod_path}")
    return src


def _reload_and_resolve(target: str) -> AgentManifest:
    """热重载作者模块并重新解析 manifest。先清掉该模块在 _DECLARED 的登记，使 reload 重新执行
    @agent 时不撞"重复声明的 agent key"。"""
    mod_path = target.partition(":")[0]
    from chameleon.agentkit import _decorator

    for k, m in list(_decorator._DECLARED.items()):
        if getattr(m.handler, "__module__", "").startswith(mod_path):
            _decorator._DECLARED.pop(k, None)
    importlib.invalidate_caches()  # 清 finder 缓存，确保 reload 见到文件变更
    importlib.reload(sys.modules[mod_path])
    return _load_manifest(target)


def _cmd_dev(target: str, text: str, interval: float = 0.5) -> int:
    """watch 源文件 mtime，改动即热重载 + 重跑——本地编辑 agent 的即时反馈闭环。"""
    man = _load_manifest(target)
    src = _module_source(target.partition(":")[0])
    print(f"{_CYAN}agentkit dev{_RESET} · {man.name} ({man.key}) · watch {src} · Ctrl-C 退出")
    asyncio.run(_invoke(man, text, []))
    last = os.path.getmtime(src)
    try:
        while True:
            time.sleep(interval)
            try:
                cur = os.path.getmtime(src)
            except OSError:
                continue  # 编辑器原子写瞬间文件可能不存在，跳过本轮
            if cur == last:
                continue
            last = cur
            print(f"\n{_DIM}── 源文件变更，热重载重跑 ──{_RESET}")
            try:
                man = _reload_and_resolve(target)
                asyncio.run(_invoke(man, text, []))
            except Exception as e:  # noqa: BLE001 —— 作者改出语法/运行错不该崩 watch 循环
                print(f"{_DIM}✗ 重载失败（修正后保存即重试）：{type(e).__name__}: {e}{_RESET}")
    except KeyboardInterrupt:
        print()
        return 0


def _cmd_test(target: str, query: str) -> int:
    """零配置 smoke：用 FakeTransport（确定性、不连平台/不打真 LLM）把 agent 跑一遍，断言
    「能跑通 + 有产出」，并摘要资源调用次数。作者写正式单测见 chameleon.agentkit.testing
    （FakeTransport + make_run + collect），用 pytest 跑。"""
    from chameleon.agentkit.testing import FakeTransport, collect, make_run

    man = _load_manifest(target)
    fake = FakeTransport(replies=["（agentkit test 占位回复）"])
    opt_defaults = {o.key: o.default for o in (man.config or []) if o.default is not None}
    run = make_run(man.handler, query=query, transport=fake, config=opt_defaults)
    handler = man.handler
    if man.is_class and not hasattr(handler, "handle"):
        print(f"✗ {man.key}: 旧式 astream 类不支持 smoke（请用 handle(self, run) 范式或 pytest 自测）")
        return 1
    try:
        result = handler().handle(run) if man.is_class else handler(run)
        out = asyncio.run(collect(result))
    except Exception as e:  # noqa: BLE001 —— smoke 的全部价值就是抓住"基本查询就崩"
        print(f"✗ smoke {man.key} 失败：{type(e).__name__}: {e}")
        return 1
    ok = bool(out and out.strip())
    mark = f"{_CYAN}✓{_RESET}" if ok else "✗"
    print(
        f"{mark} smoke {man.key}: {'跑通' if ok else '跑通但无产出'}"
        f"{f'，产出 {len(out)} 字' if ok else ''}"
    )
    print(
        f"  {_DIM}查询 “{query}” · 资源调用 {len(fake.invocations)} 次 · "
        f"FakeTransport（无真 LLM/平台）{_RESET}"
    )
    return 0 if ok else 1


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
    for name in ("lint", "run", "chat", "dev", "test"):
        p = sub.add_parser(name)
        p.add_argument("target", help="作者模块，如 my_pkg.agent 或 my_pkg.agent:handle")
        if name in ("run", "dev"):
            p.add_argument("-i", "--input", required=True, help="单次输入（dev 下每次热重载重跑它）")
        if name == "test":
            p.add_argument("-i", "--input", default="你好", help="smoke 查询（默认“你好”）")
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
    if ns.cmd == "dev":
        return _cmd_dev(ns.target, ns.input)
    if ns.cmd == "test":
        return _cmd_test(ns.target, ns.input)
    if ns.cmd == "new":
        return _cmd_new(ns.name, ns.dir)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

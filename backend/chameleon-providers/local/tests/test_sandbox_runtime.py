"""沙箱生产 parent run_sandboxed e2e（T4-2 Phase 2 Slice 1b-2）：fake broker + 真子进程。"""

from __future__ import annotations

import sys
import textwrap

import pytest

from chameleon.providers.base.types import StreamEventType
from chameleon.providers.local.sandbox import run_sandboxed

_DOCKER_AGENT = textwrap.dedent(
    '''
    import os
    from chameleon.agentkit import agent, AgentRun, ModelSlot

    @agent(key="dkr-iso", name="t", models=[ModelSlot("chat", "c")])
    async def handle(ctx: AgentRun):
        db = os.environ.get("DATABASE_URL", "<scrubbed>")
        ans = await ctx.complete(system="s", user=ctx.query)
        yield f"{ans}|db={db}"
    '''
)

_AGENT = textwrap.dedent(
    '''
    from chameleon.agentkit import agent, AgentRun, ModelSlot

    @agent(key="_sbx_rt", name="t", models=[ModelSlot("chat", "c")])
    async def handle(ctx: AgentRun):
        ans = await ctx.complete(system="s", user=ctx.query)
        yield "答:" + ans
    '''
)


class _FakeMsg:
    def __init__(self, content):
        self.content = content


class _FakeModel:
    async def ainvoke(self, messages, **_kw):
        # 校验有 user 消息过线（不绑定具体内容，便于多用例复用）
        assert any(isinstance(m, tuple) and m[0] == "user" for m in messages)
        return _FakeMsg("BROKER_RESOLVED")

    async def astream(self, messages, **_kw):
        for piece in ("流", "式", "块"):
            yield _FakeMsg(piece)


class _FakeBroker:
    def chat_model(self, *, slot=None, model=None):
        return _FakeModel()


_STREAM_AGENT = textwrap.dedent(
    '''
    from chameleon.agentkit import agent, AgentRun, ModelSlot

    @agent(key="_sbx_stream", name="t", models=[ModelSlot("chat", "c")])
    async def handle(ctx: AgentRun):
        async for d in ctx.stream(system="s", user=ctx.query):
            yield d
    '''
)


@pytest.mark.asyncio
async def test_run_sandboxed_parent_loop_and_broker(tmp_path):
    (tmp_path / "sbx_rt_mod.py").write_text(_AGENT, encoding="utf-8")
    events = []
    async for ev in run_sandboxed(
        module="sbx_rt_mod",
        attr="handle",
        query="杭州",
        broker=_FakeBroker(),
        env_extra={"PYTHONPATH": __import__("os").pathsep.join([str(tmp_path), *sys.path])},
    ):
        events.append(ev)
    deltas = [e.data.get("text", "") for e in events if e.type == StreamEventType.delta]
    assert "".join(deltas) == "答:BROKER_RESOLVED"  # 子进程 ctx.complete 经 broker 解析回流
    assert not any(e.type == StreamEventType.error for e in events)


def test_resolve_agent_mount_scopes_to_package():
    """评审5 #31：只挂 agent 自己的包（防 prod site-packages over-mount 跨租户源码泄漏）。"""
    from chameleon.providers.local.sandbox.runtime import _resolve_agent_mount

    # 真实命名空间包 agent
    mount = _resolve_agent_mount("chameleon.agents.example_classic.agent")
    assert mount is not None
    host, container = mount
    assert host.endswith("chameleon/agents/example_classic")  # 只挂该包，非 src 根/site-packages
    assert container == "/agent_src/chameleon/agents/example_classic"
    assert "site-packages" not in container


def test_build_docker_command_isolation_flags():
    """Phase 3 docker 命令烘焙全部隔离 flags（真不可信隔离的安全核心，含评审5 加固）。"""
    from chameleon.providers.local.sandbox import build_docker_command

    cmd = build_docker_command("chm-sbx:latest", "/host/agent/src", mem_mb=256, name="chm-sbx-x")
    s = " ".join(cmd)
    assert "--network none" in s  # 无网络出站（防 SSRF/外传）
    assert "--read-only" in s  # 只读 rootfs（host .env/config 不挂入→读不到盘上凭据）
    assert "--user 65534:65534" in s  # 非 root（评审5 加固：与下层 runtime 对齐）
    assert "--cap-drop ALL" in s  # 清空 capability（评审5 加固）
    assert "--memory 256m" in s and "--pids-limit 256" in s  # 内存/进程限
    assert "--security-opt no-new-privileges" in s
    assert "--name chm-sbx-x" in s  # 确定性清理（finally docker kill 兜底）
    assert "/host/agent/src:/agent_src:ro" in s  # agent 源码只读挂载
    # 不挂 config/凭据目录、不传 host 凭据 env
    assert "component.json" not in s and "DATABASE_URL" not in s
    assert cmd[-3:] == ["python", "-m", "chameleon.agentkit._sandbox_child"]


def _docker_image_ready(image: str) -> bool:
    import shutil
    import subprocess

    if not shutil.which("docker"):
        return False
    try:
        r = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True, timeout=10,
        )
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


_SBX_IMAGE = "chm-agent-sandbox:lean"


@pytest.mark.skipif(
    not _docker_image_ready(_SBX_IMAGE),
    reason=f"需 docker + 预构镜像 {_SBX_IMAGE}（CI 先 docker build -f docker/sandbox.Dockerfile）",
)
@pytest.mark.asyncio
async def test_run_sandboxed_docker_real_isolation(tmp_path, monkeypatch):
    """真 docker 容器隔离 e2e：handle 在 --network none --read-only 容器跑，读不到 host 凭据。"""
    (tmp_path / "dkr_iso_mod.py").write_text(_DOCKER_AGENT, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))  # find_spec 定位 agent 源码
    monkeypatch.setenv("CHAMELEON_SANDBOX_RUNTIME", "docker")
    monkeypatch.setenv("CHAMELEON_SANDBOX_IMAGE", _SBX_IMAGE)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://secret:pw@h:5432/db")  # 容器不应见
    deltas = []
    async for ev in run_sandboxed(
        module="dkr_iso_mod", attr="handle", query="hi", broker=_FakeBroker(),
    ):
        if ev.type == StreamEventType.delta:
            deltas.append(ev.data.get("text", ""))
    text = "".join(deltas)
    assert "BROKER_RESOLVED" in text  # broker over docker stdio 往返通
    assert "db=<scrubbed>" in text  # 容器读不到 host DATABASE_URL（FS/env 真隔离）


@pytest.mark.asyncio
async def test_broker_run_tool_scope_rejects_undeclared():
    """broker scope 红线：子进程调未声明的平台工具 → 拒绝（不执行）。"""
    from chameleon.providers.local.sandbox.runtime import _resolve_rpc

    class _Broker:
        _tool_keys = ["http"]  # 只声明了 http

    # 调声明外的工具 → 越权拒
    res = await _resolve_rpc(_Broker(), {"method": "run_tool", "args": {"name": "sql", "args": {}}})
    assert res["ok"] is False and "越权" in res["error"]


@pytest.mark.asyncio
async def test_broker_kb_scope_filters_unlinked(monkeypatch):
    """kb scope：点名的 kbs ∩ agent 关联 KB，越权的剔除（防检索他人知识库）。"""
    from chameleon.providers.local.sandbox import runtime as rt

    async def _fake_linked(agent_key):
        return [type("M", (), {"kb_key": "kb-allowed"})()]

    monkeypatch.setattr("chameleon.integrations.knowledge.list_linked_kb_metas", _fake_linked)
    received: dict = {}

    class _Broker:
        _agent_key = "a"

        async def kb_search(self, query, *, kbs=None, **kw):  # noqa: ANN001, ANN002, ANN003
            received["kbs"] = kbs
            return []

    await rt._resolve_rpc(
        _Broker(), {"method": "kb_search", "args": {"query": "q", "kbs": ["kb-allowed", "kb-越权"]}}
    )
    assert received["kbs"] == ["kb-allowed"]  # 越权 kb-越权 被剔除


@pytest.mark.asyncio
async def test_broker_scope_model_and_empty_tools():
    """评审修复：model 点名未声明 → 拒；空工具声明 → 全拒（不再全放行）。"""
    from chameleon.providers.local.sandbox.runtime import _resolve_rpc

    class _Broker:
        _bindings = {"chat": "qwen-plus"}
        _tool_keys: list = []

    # model 点名未声明 → 越权拒（防烧钱）
    r1 = await _resolve_rpc(_Broker(), {"method": "chat", "args": {"model": "gpt-4o-贵", "messages": []}})
    assert r1["ok"] is False and "越权" in r1["error"]
    # 空工具声明 → 任意工具全拒
    r2 = await _resolve_rpc(_Broker(), {"method": "run_tool", "args": {"name": "http", "args": {}}})
    assert r2["ok"] is False and "越权" in r2["error"]


@pytest.mark.asyncio
async def test_broker_call_agent_allowlist():
    """call_agent allow-list：沙箱只能调声明的子 agent，未声明 target 拒。"""
    from chameleon.providers.local.sandbox.runtime import _resolve_rpc

    called: dict = {}

    class _Broker:
        _call_agents = ["sub-ok"]

        async def call_agent(self, target, *, input):  # noqa: ANN001
            called["t"] = target
            return "子答案"

    # 声明内 → 通
    ok = await _resolve_rpc(_Broker(), {"method": "call_agent", "args": {"target": "sub-ok", "input": "q"}})
    assert ok["ok"] is True and ok["data"] == "子答案" and called["t"] == "sub-ok"
    # 声明外 → 越权拒（未真调）
    called.clear()
    bad = await _resolve_rpc(_Broker(), {"method": "call_agent", "args": {"target": "any-other", "input": "q"}})
    assert bad["ok"] is False and "越权" in bad["error"] and "t" not in called


@pytest.mark.asyncio
async def test_run_sandboxed_streaming(tmp_path):
    (tmp_path / "sbx_stream_mod.py").write_text(_STREAM_AGENT, encoding="utf-8")
    deltas = []
    async for ev in run_sandboxed(
        module="sbx_stream_mod", attr="handle", query="杭州", broker=_FakeBroker(),
        env_extra={"PYTHONPATH": __import__("os").pathsep.join([str(tmp_path), *sys.path])},
    ):
        if ev.type == StreamEventType.delta:
            deltas.append(ev.data.get("text", ""))
    # 子进程 ctx.stream → chat_stream rpc → broker.astream 多块经 stream_chunk 帧回流
    assert "".join(deltas) == "流式块"

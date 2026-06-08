"""验证 examples/standalone_orchestration.py 正确——假模型跑 ctx.gather 并行扇出，不需真 LLM。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from chameleon.agentkit.standalone import StandaloneTransport, run_standalone

_EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "standalone_orchestration.py"


def _load():
    spec = importlib.util.spec_from_file_location("_sa_orch_example", _EXAMPLE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # 顶层不含 langchain_openai（main() 内惰性）
    return mod


_MOD = _load()  # @agent key 全局唯一，模块级加载一次


class _Msg:
    def __init__(self, content):
        self.content = content


class _FakeModel:
    """据 system 含'正方'/'反方'返不同观点，验两个子 agent 都真跑到。"""

    async def ainvoke(self, messages, **_kw):
        sys_text = " ".join(c for r, c in messages if r == "system")
        if "正方" in sys_text:
            return _Msg("支持理由X")
        if "反方" in sys_text:
            return _Msg("反对理由Y")
        return _Msg("?")

    async def astream(self, messages, **_kw):
        yield _Msg("?")

    def with_structured_output(self, schema):
        return self

    def bind_tools(self, tools):
        return self


@pytest.mark.asyncio
async def test_example_orchestration_gathers_both_specialists():
    """主持 agent 经 ctx.gather 并行扇出到正/反两个本地子 agent，综合两方观点。"""
    t = StandaloneTransport(
        model=_FakeModel(),
        agents={"pros-bot": _MOD.pros, "cons-bot": _MOD.cons},
    )
    out = await run_standalone(_MOD.debate, "公司是否该全面远程办公", transport=t)
    assert "支持理由X" in out and "反对理由Y" in out  # 两个子 agent 都被并行调到并综合
    assert "正方" in out and "反方" in out

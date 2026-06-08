"""验证 examples/standalone_rag.py 示例正确（无 API 漂移）——用假模型跑其 handle，不需真 LLM。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from chameleon.agentkit._spec import Doc
from chameleon.agentkit.standalone import StandaloneTransport, run_standalone

_EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "standalone_rag.py"


def _load_example():
    # 模块级加载一次：@agent key 全局唯一，重复 exec_module 会撞 '重复声明' ValueError。
    spec = importlib.util.spec_from_file_location("_sa_rag_example", _EXAMPLE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # 顶层 import 不含 langchain_openai（在 main() 内惰性）
    return mod


_MOD = _load_example()


class _Msg:
    def __init__(self, content):
        self.content = content


class _FakeModel:
    """鸭子类型 chat model：astream 把 system 里的资料原样回吐（验上下文真被喂进去）。"""

    async def astream(self, messages, **_kw):
        # messages 末条 user 含拼好的 context；这里简单回一句固定答案验链路通
        yield _Msg("据资料：")
        yield _Msg("agentkit 用 StandaloneTransport 脱平台跑")

    async def ainvoke(self, messages, **_kw):
        return _Msg("x")

    def with_structured_output(self, schema):
        return self

    def bind_tools(self, tools):
        return self


@pytest.mark.asyncio
async def test_example_rag_answers_from_kb():
    """示例 handle：kb 命中 → 拼上下文 → 流式作答。"""
    mod = _MOD
    t = StandaloneTransport(model=_FakeModel(), kb_docs=mod.MY_DOCS)
    out = await run_standalone(mod.handle, "agentkit 怎么脱平台跑", transport=t)
    assert "StandaloneTransport" in out  # 走了检索+作答链路


@pytest.mark.asyncio
async def test_example_rag_no_hit_says_unknown():
    """示例 handle：kb 无命中 → 明说不知道（不编造）。"""
    mod = _MOD
    t = StandaloneTransport(model=_FakeModel(), kb_docs=[Doc(text="完全无关的内容 xyz")])
    out = await run_standalone(mod.handle, "火星上有几个月亮", transport=t)
    assert "无法回答" in out or "没有相关" in out

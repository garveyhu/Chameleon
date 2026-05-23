"""装饰器 + auto-patch —— P22.2 PR #76

提供：
- @trace(client, name) / @span(name) 装饰函数
- patch_openai(client)：monkey-patch openai client 自动 trace

红线：默认 client 通过 module-level get_default_client() 取；调用方必须
显式 set 一次 default。
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, Callable, TypeVar

if TYPE_CHECKING:
    from chameleon_sdk.client import Client

_default_client: "Client | None" = None
F = TypeVar("F", bound=Callable[..., Any])


def set_default_client(client: "Client") -> None:
    """设置全局默认 client；装饰器和 patch_openai 用它"""
    global _default_client
    _default_client = client


def get_default_client() -> "Client":
    if _default_client is None:
        raise RuntimeError(
            "default Client 未设置；先调 set_default_client(Client(...))"
        )
    return _default_client


def trace(name: str | None = None) -> Callable[[F], F]:
    """函数装饰器：自动起一个 trace 包整个调用

    @trace(name="my-job")
    def my_job(...):
        ...
    """

    def deco(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            c = get_default_client()
            with c.trace(name or fn.__name__):
                return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return deco


def span(name: str | None = None, observation_type: str = "span") -> Callable[[F], F]:
    """函数装饰器：在当前 trace 里加一个 span（无 trace 时报错）

    必须配合 @trace 或外层 with client.trace():
    """

    def deco(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            c = get_default_client()
            # 取栈顶 trace；用 trace.span()
            # 简化：要求调用方已经在 with trace 内（默认 client 暂不维护 trace 栈）
            raise NotImplementedError(
                "@span 暂未实现栈管理；请用 with trace.span() 上下文管理器"
            )

        return wrapper  # type: ignore[return-value]

    return deco


# ── auto-patch: openai ─────────────────────────────────


def patch_openai(client: "Client | None" = None) -> None:
    """Monkey-patch openai SDK 自动 trace chat.completions.create

    在 import openai 后调用：
        from chameleon_sdk import Client, patch_openai
        c = Client(api_key="...")
        patch_openai(c)
        # 之后 openai.chat.completions.create() 自动出现在 chameleon trace
    """
    try:
        from openai.resources.chat.completions import Completions
    except ImportError:
        raise RuntimeError(
            "openai package not installed; pip install openai>=1.0"
        )

    c = client or get_default_client()
    original_create = Completions.create

    def patched_create(self, *args, **kwargs):
        model = kwargs.get("model") or (args[0] if args else None)
        # 用 client 直接创一个 trace + span（每次 call 独立 trace）
        with c.trace(name="openai.chat.completion") as t:
            with t.span(
                name="openai.chat.completion",
                observation_type="generation",
            ) as sp:
                if model:
                    sp.set_model(model)
                try:
                    result = original_create(self, *args, **kwargs)
                except Exception as e:
                    sp.set_status(2, str(e)[:200])
                    raise
                # 抽 usage
                usage = getattr(result, "usage", None)
                if usage:
                    sp.set_usage(
                        prompt_tokens=getattr(usage, "prompt_tokens", None),
                        completion_tokens=getattr(usage, "completion_tokens", None),
                        total_tokens=getattr(usage, "total_tokens", None),
                    )
                return result

    Completions.create = patched_create  # type: ignore[assignment]


def patch_all(client: "Client | None" = None) -> None:
    """一键装所有可用的 patch"""
    c = client or get_default_client()
    try:
        patch_openai(c)
    except RuntimeError:
        # openai 没装，跳过
        pass

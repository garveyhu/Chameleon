"""Chameleon Python SDK —— P22.2 PR #74

Quickstart:

    from chameleon_sdk import Client

    client = Client(api_key="sk-...", base_url="http://localhost:7009")

    with client.trace(name="my-trace") as trace:
        with trace.span(name="step-1", observation_type="generation") as span:
            # ... call openai / claude here
            span.set_usage(prompt_tokens=100, completion_tokens=50)
            span.set_model("gpt-4o-mini")

    client.flush()  # 显式 flush；进程退出时 atexit 也会 flush

Async variant:

    from chameleon_sdk import AsyncClient

    async with AsyncClient(api_key="...") as client:
        async with client.trace() as t:
            async with t.span(name="...") as s:
                ...
"""

from chameleon_sdk.client import AsyncClient, Client
from chameleon_sdk.decorators import (
    get_default_client,
    patch_all,
    patch_openai,
    set_default_client,
    trace,
)
from chameleon_sdk.tracer import Span, Trace

__version__ = "0.1.0"

__all__ = [
    "AsyncClient",
    "Client",
    "Span",
    "Trace",
    "get_default_client",
    "patch_all",
    "patch_openai",
    "set_default_client",
    "trace",
]

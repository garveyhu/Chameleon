# Chameleon Python SDK

LLMops tracing & instrumentation for Chameleon.

## Install

```bash
pip install chameleon-sdk
```

## Quickstart (sync)

```python
from chameleon_sdk import Client

client = Client(api_key="sk-...", base_url="http://localhost:7009")

with client.trace(name="my-pipeline") as trace:
    with trace.span("retrieve-kb", observation_type="retriever") as sp:
        sp.set_attribute("kb_id", "smoke")
    with trace.span("llm-call", observation_type="generation") as sp:
        sp.set_model("gpt-4o-mini")
        sp.set_usage(prompt_tokens=200, completion_tokens=100)

client.flush()  # 进程退出时 atexit 也会 flush
```

## Quickstart (async)

```python
from chameleon_sdk import AsyncClient

async with AsyncClient(api_key="sk-...") as client:
    async with client.trace(name="async-pipeline") as t:
        with t.span("llm-call", observation_type="generation") as sp:
            sp.set_model("gpt-4o")
            sp.set_usage(prompt_tokens=100, completion_tokens=50)
```

## Configuration

| Env var | Default | 含义 |
|---------|---------|------|
| `CHAMELEON_API_KEY` | — | Required if not passed to `Client(api_key=...)` |
| `CHAMELEON_BASE_URL` | `http://localhost:7009` | Chameleon backend URL |

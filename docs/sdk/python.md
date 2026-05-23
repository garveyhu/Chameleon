# Chameleon Python SDK

LLMops tracing & instrumentation. Works on Python 3.9+.

## Install

```bash
pip install chameleon-sdk
```

## Quickstart

```python
from chameleon_sdk import Client

client = Client(api_key="sk-...", base_url="http://localhost:7009")

with client.trace(name="my-pipeline") as trace:
    with trace.span("retrieve-kb", observation_type="retriever") as sp:
        sp.set_attribute("kb_id", "smoke")

    with trace.span("llm-call", observation_type="generation") as sp:
        sp.set_model("gpt-4o-mini")
        sp.set_usage(prompt_tokens=200, completion_tokens=100)

client.flush()
```

## Async usage

```python
from chameleon_sdk import AsyncClient

async def main():
    async with AsyncClient(api_key="...") as client:
        async with client.trace("async-pipeline") as t:
            with t.span("llm", observation_type="generation") as sp:
                sp.set_model("gpt-4o")
                sp.set_usage(prompt_tokens=100, completion_tokens=50)
```

## Decorator

```python
from chameleon_sdk import Client, set_default_client, trace

client = Client(api_key="sk-...")
set_default_client(client)

@trace(name="my-job")
def my_job(x):
    return x * 2

my_job(21)  # 自动建一个 trace；进程退出时 atexit 上报
```

## auto-patch（OpenAI）

```python
import openai
from chameleon_sdk import Client, set_default_client, patch_openai

client = Client(api_key="sk-...")
set_default_client(client)
patch_openai(client)  # monkey-patch openai.chat.completions.create

# 之后任何 openai 调用都自动出现在 chameleon trace
openai_client = openai.OpenAI()
openai_client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "hi"}],
)

client.flush()
```

`patch_all(client)` 一键装所有可用的 patch（openai 未装时静默跳过）。

## Configuration

| Env var | Default | 含义 |
|---------|---------|------|
| `CHAMELEON_API_KEY` | — | API key（不传 `api_key=` 时兜底） |
| `CHAMELEON_BASE_URL` | `http://localhost:7009` | Backend URL |

## ObservationType 枚举

`trace` / `span` / `generation` / `agent` / `tool` / `retriever` / `embedding` / `evaluator` / `guardrail`

写到 `chameleon.observation_type` 属性，让 backend converter 识别。

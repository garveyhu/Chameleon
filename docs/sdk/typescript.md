# Chameleon TypeScript SDK

LLMops tracing for Node 18+ and modern browsers.

## Install

```bash
npm install @chameleon/sdk
# or
yarn add @chameleon/sdk
```

## Quickstart

```typescript
import { ChameleonClient } from '@chameleon/sdk';

const client = new ChameleonClient({
  apiKey: 'sk-...',
  baseUrl: 'http://localhost:7009',
});

await client.withTrace('my-pipeline', async (trace) => {
  await trace.withSpan('retrieve', { observationType: 'retriever' }, async (sp) => {
    sp.setAttribute('kb_id', 'smoke');
  });

  await trace.withSpan('llm-call', { observationType: 'generation' }, async (sp) => {
    sp.setModel('gpt-4o-mini');
    sp.setUsage({ promptTokens: 200, completionTokens: 100 });
  });
});

await client.flush();
```

## Manual span control

```typescript
const trace = client.trace('manual');
const sp = trace.startSpan('inner', { observationType: 'tool' });
sp.setAttribute('arg', 'hi');
trace.finishSpan(sp);
trace._close();
await client.flush();
```

## Browser usage

SDK 在 browser 环境也能跑，但通常**不推荐**在前端直接持 apiKey；建议通过后端 BFF 代理。

## Configuration

| Env var | Default | 含义 |
|---------|---------|------|
| `CHAMELEON_API_KEY` | — | API key（仅在 Node 端读 process.env） |
| `CHAMELEON_BASE_URL` | `http://localhost:7009` | Backend URL |

## ObservationType

`trace` / `span` / `generation` / `agent` / `tool` / `retriever` / `embedding` / `evaluator` / `guardrail`

写到 `chameleon.observation_type` 属性自动设置（在 Span 构造时）。

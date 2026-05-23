# Chameleon TypeScript SDK

LLMops tracing for Chameleon. Works in Node 18+ and modern browsers.

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

await client.flush(); // 显式 flush 上报到 backend
```

## Configuration

| Env var | Default | 说明 |
|---------|---------|------|
| `CHAMELEON_API_KEY` | — | API key（如未传 `apiKey`） |
| `CHAMELEON_BASE_URL` | `http://localhost:7009` | Backend URL |

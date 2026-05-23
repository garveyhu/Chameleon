/**
 * Chameleon TypeScript SDK — P22.2 PR #75
 *
 * Quickstart:
 *
 *     import { ChameleonClient } from '@chameleon/sdk';
 *
 *     const client = new ChameleonClient({
 *       apiKey: 'sk-...',
 *       baseUrl: 'http://localhost:7009',
 *     });
 *
 *     await client.withTrace('my-pipeline', async (trace) => {
 *       await trace.withSpan('retrieve', { observationType: 'retriever' }, async (sp) => {
 *         sp.setAttribute('kb_id', 'smoke');
 *       });
 *       await trace.withSpan('llm-call', { observationType: 'generation' }, async (sp) => {
 *         sp.setModel('gpt-4o-mini');
 *         sp.setUsage({ promptTokens: 200, completionTokens: 100 });
 *       });
 *     });
 *
 *     await client.flush();
 */

export { ChameleonClient } from './client.js';
export { Span, Trace } from './tracer.js';
export type {
  ChameleonClientOptions,
  ObservationType,
  SpanOptions,
  UsageInput,
} from './types.js';

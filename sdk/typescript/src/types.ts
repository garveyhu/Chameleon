/** Chameleon SDK 类型定义 —— P22.2 PR #75 */

export type ObservationType =
  | 'trace'
  | 'span'
  | 'generation'
  | 'agent'
  | 'tool'
  | 'retriever'
  | 'embedding'
  | 'evaluator'
  | 'guardrail';

export interface ChameleonClientOptions {
  /** API key（required；可通过 CHAMELEON_API_KEY env var 兜底） */
  apiKey?: string;
  /** Backend base URL；默认 http://localhost:7009 */
  baseUrl?: string;
  /** OTLP resource.service.name */
  serviceName?: string;
  /** 自动 fetch 实现（默认 globalThis.fetch；测试可 mock 注入） */
  fetchImpl?: typeof fetch;
}

export interface SpanOptions {
  observationType?: ObservationType;
  attributes?: Record<string, string | number | boolean>;
}

export interface UsageInput {
  promptTokens?: number;
  completionTokens?: number;
  totalTokens?: number;
}

// OTLP minimal JSON shapes（与后端 schemas 对齐）

export interface OtlpAnyValue {
  stringValue?: string;
  boolValue?: boolean;
  intValue?: string;
  doubleValue?: number;
}

export interface OtlpKeyValue {
  key: string;
  value: OtlpAnyValue;
}

export interface OtlpSpan {
  traceId: string;
  spanId: string;
  parentSpanId?: string;
  name: string;
  kind: number;
  startTimeUnixNano: string;
  endTimeUnixNano: string;
  attributes: OtlpKeyValue[];
  status: { code: number; message?: string };
}

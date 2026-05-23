/** Trace / Span —— P22.2 PR #75 */

import type {
  ObservationType,
  OtlpKeyValue,
  OtlpSpan,
  SpanOptions,
  UsageInput,
} from './types.js';

function hex(nbytes: number): string {
  const bytes = new Uint8Array(nbytes);
  const cryptoLib = (globalThis as { crypto?: Crypto }).crypto;
  if (!cryptoLib) {
    throw new Error('globalThis.crypto unavailable (Node >= 18 required)');
  }
  cryptoLib.getRandomValues(bytes);
  return Array.from(bytes)
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

function kv(key: string, value: string | number | boolean): OtlpKeyValue {
  if (typeof value === 'boolean') {
    return { key, value: { boolValue: value } };
  }
  if (typeof value === 'number' && Number.isInteger(value)) {
    return { key, value: { intValue: String(value) } };
  }
  if (typeof value === 'number') {
    return { key, value: { doubleValue: value } };
  }
  return { key, value: { stringValue: String(value) } };
}

interface ClientShim {
  bufferSpan(span: OtlpSpan): void;
}

export class Span {
  readonly traceId: string;
  readonly spanId: string;
  readonly parentSpanId: string | null;
  readonly name: string;
  readonly observationType: ObservationType;
  private readonly startUnixNano: bigint;
  private endUnixNano: bigint | null = null;
  private attributes: Record<string, string | number | boolean> = {};
  private statusCode = 1; // 1=Ok, 2=Error
  private statusMessage: string | null = null;

  constructor(
    name: string,
    traceId: string,
    parentSpanId: string | null,
    observationType: ObservationType = 'span',
  ) {
    this.traceId = traceId;
    this.spanId = hex(8);
    this.parentSpanId = parentSpanId;
    this.name = name;
    this.observationType = observationType;
    this.startUnixNano = BigInt(Date.now()) * 1_000_000n;
    // 标记 observation_type 让后端 converter 识别
    this.attributes['chameleon.observation_type'] = observationType;
  }

  setAttribute(key: string, value: string | number | boolean): this {
    this.attributes[key] = value;
    return this;
  }

  setUsage(u: UsageInput): this {
    if (u.promptTokens != null) {
      this.attributes['gen_ai.usage.prompt_tokens'] = u.promptTokens;
    }
    if (u.completionTokens != null) {
      this.attributes['gen_ai.usage.completion_tokens'] = u.completionTokens;
    }
    if (u.totalTokens != null) {
      this.attributes['gen_ai.usage.total_tokens'] = u.totalTokens;
    }
    return this;
  }

  setModel(model: string, system = 'openai'): this {
    this.attributes['gen_ai.request.model'] = model;
    this.attributes['gen_ai.system'] = system;
    return this;
  }

  setStatus(code: 1 | 2, message?: string): this {
    this.statusCode = code;
    this.statusMessage = message ?? null;
    return this;
  }

  finish(): void {
    if (this.endUnixNano !== null) return; // 防重复 finish
    this.endUnixNano = BigInt(Date.now()) * 1_000_000n;
  }

  toOtlp(): OtlpSpan {
    if (this.endUnixNano === null) {
      this.endUnixNano = BigInt(Date.now()) * 1_000_000n;
    }
    const attrs: OtlpKeyValue[] = Object.entries(this.attributes).map(
      ([k, v]) => kv(k, v),
    );
    return {
      traceId: this.traceId,
      spanId: this.spanId,
      ...(this.parentSpanId ? { parentSpanId: this.parentSpanId } : {}),
      name: this.name,
      kind: 1,
      startTimeUnixNano: this.startUnixNano.toString(),
      endTimeUnixNano: this.endUnixNano.toString(),
      attributes: attrs,
      status: {
        code: this.statusCode,
        ...(this.statusMessage ? { message: this.statusMessage } : {}),
      },
    };
  }
}

export class Trace {
  readonly traceId: string;
  private readonly name: string;
  private readonly client: ClientShim;
  private readonly stack: Span[] = [];

  constructor(name: string, client: ClientShim) {
    this.name = name;
    this.client = client;
    this.traceId = hex(16);
    const root = new Span(name, this.traceId, null, 'trace');
    this.stack.push(root);
  }

  /** Use with `withSpan` 推荐；手动 startSpan/finish 也可以 */
  startSpan(name: string, opts: SpanOptions = {}): Span {
    const parent = this.stack[this.stack.length - 1] ?? null;
    const sp = new Span(
      name,
      this.traceId,
      parent ? parent.spanId : null,
      opts.observationType ?? 'span',
    );
    if (opts.attributes) {
      for (const [k, v] of Object.entries(opts.attributes)) {
        sp.setAttribute(k, v);
      }
    }
    this.stack.push(sp);
    return sp;
  }

  finishSpan(sp: Span): void {
    sp.finish();
    // 从 stack pop（如果在）
    const idx = this.stack.lastIndexOf(sp);
    if (idx >= 0) this.stack.splice(idx, 1);
    this.client.bufferSpan(sp.toOtlp());
  }

  async withSpan<T>(
    name: string,
    opts: SpanOptions,
    fn: (span: Span) => Promise<T> | T,
  ): Promise<T> {
    const sp = this.startSpan(name, opts);
    try {
      return await fn(sp);
    } catch (e) {
      sp.setStatus(2, String((e as Error)?.message ?? e).slice(0, 200));
      throw e;
    } finally {
      this.finishSpan(sp);
    }
  }

  /** Internal: trace 结束时关闭 root span */
  _close(error?: Error): void {
    const root = this.stack[0];
    if (root) {
      if (error) {
        root.setStatus(2, String(error.message ?? error).slice(0, 200));
      }
      root.finish();
      this.client.bufferSpan(root.toOtlp());
    }
    this.stack.length = 0;
  }
}

/** ChameleonClient —— P22.2 PR #75
 *
 * 异步默认；提供 withTrace 帮助函数 + 手动 flush。
 */

import { Trace } from './tracer.js';
import type {
  ChameleonClientOptions,
  OtlpSpan,
} from './types.js';

const MAX_BATCH = 5000;
const SDK_VERSION = '0.1.0';

export class ChameleonClient {
  readonly apiKey: string;
  readonly baseUrl: string;
  readonly serviceName: string;
  private readonly fetchImpl: typeof fetch;
  private buffer: OtlpSpan[] = [];

  constructor(options: ChameleonClientOptions = {}) {
    const proc = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process;
    const envKey = proc?.env?.CHAMELEON_API_KEY;
    const envUrl = proc?.env?.CHAMELEON_BASE_URL;
    const key = options.apiKey ?? envKey;
    if (!key) {
      throw new Error(
        'apiKey is required (or set CHAMELEON_API_KEY env var)',
      );
    }
    this.apiKey = key;
    this.baseUrl = (
      options.baseUrl ?? envUrl ?? 'http://localhost:7009'
    ).replace(/\/$/, '');
    this.serviceName = options.serviceName ?? 'chameleon-sdk';
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  get tracesEndpoint(): string {
    return `${this.baseUrl}/v1/otel/v1/traces`;
  }

  /** Internal —— Trace/Span 调用 */
  bufferSpan(span: OtlpSpan): void {
    this.buffer.push(span);
  }

  /** 创建一个 trace；推荐 withTrace 包起来 */
  trace(name = 'root'): Trace {
    return new Trace(name, this);
  }

  /** with-block 语义：自动 close root span */
  async withTrace<T>(
    name: string,
    fn: (trace: Trace) => Promise<T> | T,
  ): Promise<T> {
    const t = this.trace(name);
    try {
      return await fn(t);
    } catch (e) {
      t._close(e as Error);
      throw e;
    }
    // 正常完成路径关闭 root
    finally {
      // 注意：catch 已 close 一次；finally 检查 stack 是否仍有 root
      t._close();
    }
  }

  async flush(): Promise<void> {
    while (this.buffer.length > 0) {
      const batch = this.buffer.splice(0, MAX_BATCH);
      const payload = {
        resourceSpans: [
          {
            resource: {
              attributes: [
                {
                  key: 'service.name',
                  value: { stringValue: this.serviceName },
                },
              ],
            },
            scopeSpans: [
              {
                scope: {
                  name: 'chameleon-sdk-ts',
                  version: SDK_VERSION,
                },
                spans: batch,
              },
            ],
          },
        ],
      };
      const res = await this.fetchImpl(this.tracesEndpoint, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${this.apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(
          `Chameleon OTLP upload failed: ${res.status} ${text.slice(0, 200)}`,
        );
      }
    }
  }

  // 测试用 helper
  _peekBuffer(): readonly OtlpSpan[] {
    return this.buffer;
  }
}

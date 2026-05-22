/** SSE 事件类型 + 类型守卫 —— 与后端 chameleon.core.api.sse_events 镜像
 *
 * 所有流式接口（widget invoke / models test / playground / 未来 workflow）
 * chunk 字段名遵循同一套契约。
 *
 * 字段命名沿用 wire 格式（snake_case）与后端对齐；不做 camelCase 转换。
 *
 * ## 事件总表
 * | 事件 | 形状 | 触发时机 |
 * |------|------|----------|
 * | meta | { meta: Record<string, unknown> } | 流头部 1 次 |
 * | delta | { delta: string } | 每个文本片段 |
 * | thought | { thought: ThoughtPayload } | Agent 中间步骤（P18） |
 * | citation | { citation: CitationPayload } | RAG 命中 |
 * | node_start | { node_start: NodePayload } | Workflow 节点开始（P18） |
 * | node_end | { node_end: NodePayload } | Workflow 节点结束（P18） |
 * | usage | { usage: UsagePayload } | 单独 usage 上报 |
 * | end | { end: true, usage?, ...extras } | 流末，业务字段透传 |
 * | error | { error: ErrorPayload } | 流中错误（之后不再有 end） |
 */

export interface UsagePayload {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface CitationPayload {
  source?: string;
  title?: string;
  snippet?: string;
  /** 业务自定义字段（page / char_range 等） */
  [k: string]: unknown;
}

export interface ErrorPayload {
  type: string;
  message: string;
}

export interface ThoughtPayload {
  step: number;
  tool?: string | null;
  input?: unknown;
  output?: unknown;
}

export interface NodePayload {
  node_id: string;
  node_type?: string | null;
  name?: string | null;
  status?: 'running' | 'ok' | 'error' | string;
  duration_ms?: number | null;
}

// ── 事件 wire shape ──────────────────────────────────────────

export interface MetaEvent {
  meta: Record<string, unknown>;
}
export interface DeltaEvent {
  delta: string;
}
export interface CitationEvent {
  citation: CitationPayload;
}
export interface ThoughtEvent {
  thought: ThoughtPayload;
}
export interface NodeStartEvent {
  node_start: NodePayload;
}
export interface NodeEndEvent {
  node_end: NodePayload;
}
export interface UsageEvent {
  usage: UsagePayload;
}
export interface EndEvent {
  end: true;
  usage?: UsagePayload | null;
  /** 业务扩展字段（latency_ms / answer / sample 等） */
  [k: string]: unknown;
}
export interface ErrorEvent {
  error: ErrorPayload;
}

/** 通用 SSE 事件并集 —— 流式接口统一返这个 */
export type SSEEvent =
  | MetaEvent
  | DeltaEvent
  | CitationEvent
  | ThoughtEvent
  | NodeStartEvent
  | NodeEndEvent
  | UsageEvent
  | EndEvent
  | ErrorEvent;

/** 扁平视图 —— 所有字段都可选，便于消费侧 `if (chunk.delta)` 这种简洁判别
 *
 * 用 SSEEvent 严格 union + 类型守卫是更安全的，但实际 wire 上每个 chunk 只有
 * 一个顶层 key，flat 视图等价于"分别 narrow 后再访问"，简化前端代码。
 *
 * 业务可以扩展 end 上的额外字段（latency_ms / answer / sample 等），
 * 通过 `extras` 自定义类型注入或直接 cast。
 */
export interface FlatSSEEvent {
  meta?: Record<string, unknown>;
  delta?: string;
  citation?: CitationPayload;
  thought?: ThoughtPayload;
  node_start?: NodePayload;
  node_end?: NodePayload;
  usage?: UsagePayload | null;
  end?: true;
  error?: ErrorPayload;
  /** end 业务扩展字段（latency_ms / answer / sample 等） */
  [k: string]: unknown;
}

// ── 类型守卫 ─────────────────────────────────────────────────

const has = (e: unknown, key: string): boolean =>
  typeof e === 'object' && e !== null && key in (e as object);

export const isMetaEvent = (e: SSEEvent | unknown): e is MetaEvent => has(e, 'meta');
export const isDeltaEvent = (e: SSEEvent | unknown): e is DeltaEvent =>
  has(e, 'delta') && typeof (e as DeltaEvent).delta === 'string';
export const isCitationEvent = (e: SSEEvent | unknown): e is CitationEvent =>
  has(e, 'citation');
export const isThoughtEvent = (e: SSEEvent | unknown): e is ThoughtEvent =>
  has(e, 'thought');
export const isNodeStartEvent = (e: SSEEvent | unknown): e is NodeStartEvent =>
  has(e, 'node_start');
export const isNodeEndEvent = (e: SSEEvent | unknown): e is NodeEndEvent =>
  has(e, 'node_end');
export const isUsageEvent = (e: SSEEvent | unknown): e is UsageEvent =>
  has(e, 'usage') && !has(e, 'end');
export const isEndEvent = (e: SSEEvent | unknown): e is EndEvent =>
  has(e, 'end') && (e as EndEvent).end === true;
export const isErrorEvent = (e: SSEEvent | unknown): e is ErrorEvent =>
  has(e, 'error');

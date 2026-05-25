import type { EntityId } from '@/core/types/api';

export type GraphNodeType =
  | 'noop'
  | 'start'
  | 'end'
  | 'llm'
  | 'kb'
  | 'tool'
  | 'if_else'
  | 'agent_debate'
  | 'iteration'
  | 'parallel'
  | 'human_input'
  | 'template'
  | 'answer'
  | 'http'
  | 'aggregator'
  | 'assign'
  | 'code'
  | 'classifier';

export interface NodeSpec {
  id: string;
  type: GraphNodeType;
  name?: string | null;
  data?: Record<string, unknown>;
  position?: { x: number; y: number } | null;
}

export interface EdgeSpec {
  id: string;
  source: string;
  target: string;
  source_handle?: string | null;
}

export interface GraphSpec {
  nodes: NodeSpec[];
  edges: EdgeSpec[];
}

/** 工作流形态：对话型（聊天 I/O，可发布为智能体）/ 流程型（一次性管线） */
export type GraphKind = 'chatflow' | 'workflow';

export interface GraphItem {
  id: EntityId;
  graph_key: string;
  name: string;
  description: string | null;
  kind: GraphKind;
  schema_version: number;
  enabled: boolean;
  /** P22.3：已发布版本号（0 = 从未发布） */
  published_version?: number;
  /** P22.3：最近一次发布时间 */
  published_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface GraphDetail extends GraphItem {
  spec: GraphSpec;
  /** P22.3：已发布的 spec 快照（freeze） */
  published_spec?: GraphSpec | null;
}

/** Web App / 嵌入信息（基于 embed_config） */
export interface WebAppInfo {
  id: EntityId;
  embed_key: string;
  agent_key: string;
  name: string;
  description: string | null;
  ui_config: Record<string, unknown>;
  behavior: Record<string, unknown>;
  enabled: boolean;
}

/** 智能体级 API 密钥（仅对该 agent 有效，区别于全局应用密钥） */
export interface AgentApiKey {
  id: EntityId;
  name: string;
  key_prefix: string;
  /** 明文 key（留存，支持重复复制；老数据为 null 只能看前缀） */
  plain_key: string | null;
  agent_key: string | null;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export type AgentApiKeyCreated = AgentApiKey;

export interface NodeRunItem {
  node_id: string;
  node_type: string;
  status: 'pending' | 'running' | 'success' | 'failed' | 'skipped';
  input?: unknown;
  output?: unknown;
  error?: { type: string; message: string } | null;
  duration_ms: number;
}

export interface TestRunResult {
  status: 'success' | 'failed';
  output?: unknown;
  error?: { type: string; message: string } | null;
  duration_ms: number;
  node_runs: NodeRunItem[];
}

export interface GraphRunItem {
  id: EntityId;
  graph_id: EntityId;
  request_id: string;
  session_id: string | null;
  status: 'pending' | 'running' | 'success' | 'failed' | 'cancelled' | 'paused';
  duration_ms: number | null;
  node_count: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface GraphRunDetail extends GraphRunItem {
  input?: unknown;
  output?: unknown;
  error?: { type: string; message: string } | null;
  node_runs: NodeRunItem[];
}

// ── 调试运行视图（编辑器内）─────────────────────────────────

/** 单节点在一次运行中的投影：驱动 canvas 染色 + inspector 结果区 */
export interface NodeRunView {
  status: NodeRunItem['status'];
  input?: unknown;
  output?: unknown;
  error?: { type: string; message: string } | null;
  duration_ms?: number;
  /** 流式累积的 token 文本（LLM 节点 delta，可选） */
  streamText?: string;
}

// ── test-run/stream SSE chunk（镜像后端 SSEEventKind 的 graph.* 成员）──
// wire 形状：扁平 dict { "<kind>": payload }，与 core/api/sse.py 对齐。

export interface GraphNodeEventPayload {
  node_id: string;
  node_type?: string | null;
  name?: string | null;
  status?: string | null; // running / success / failed
  duration_ms?: number | null;
  output?: unknown;
  error?: { type: string; message: string } | null;
}

export interface GraphFinishedPayload {
  status: 'success' | 'failed' | string;
  duration_ms?: number;
  node_count?: number;
  output?: unknown;
  error?: { type: string; message: string } | null;
}

/** 任一 chunk 只含一个 kind 键；前端按 key 分派。 */
export type GraphStreamChunk =
  | { 'graph.started': Record<string, unknown> }
  | { 'graph.node.started': GraphNodeEventPayload }
  | { 'graph.node.delta': { node_id: string; delta: string } }
  | { 'graph.node.finished': GraphNodeEventPayload }
  | { 'graph.node.failed': GraphNodeEventPayload }
  | { 'graph.finished': GraphFinishedPayload };

// ── 对话调试（把 draft 当可对话 agent 跑）SSE chunk ──────────
// 后端 /chat/stream 形状：{ type, data }（GraphProvider StreamEvent 镜像）

export interface GraphChatChunk {
  type: 'delta' | 'step' | 'done' | 'error' | 'citation';
  data: {
    text?: string; // delta
    name?: string; // step
    status?: string; // step
    duration_ms?: number | null;
    answer?: string; // done
    message?: string; // error
    source?: string; // citation
    snippet?: string; // citation
    score?: number | null; // citation
    [k: string]: unknown;
  };
}

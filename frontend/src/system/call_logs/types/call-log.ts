import type { EntityId } from '@/core/types/api';

export type ObservationType =
  | 'trace'
  | 'span'
  | 'generation'
  | 'agent'
  | 'tool'
  | 'retriever'
  | 'evaluator'
  | 'embedding'
  | 'guardrail';

/** 编排方式来源（join agents.source 推导） */
export type AgentSource = 'local' | 'graph' | 'dify' | 'fastgpt' | 'coze' | string;
/** 工作流形态（source=graph 时 join graphs.kind） */
export type GraphKind = 'chatflow' | 'workflow' | string;
/** 调用渠道 */
export type CallChannel = 'api' | 'openai' | 'embed' | 'playground' | 'internal' | string;

export interface CallLogItem {
  id: EntityId;
  request_id: string;
  app_id: string;
  agent_key: string;
  api_key_id?: EntityId | null;
  /** api_key 展示名（后端 join 推导；无 key 调用为 null） */
  api_key_name?: string | null;
  session_id: string | null;
  stream: boolean;
  success: boolean;
  code: number;
  error_class?: string | null;
  error_message: string | null;
  duration_ms: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  /** 会话账本维度：渠道 / 模型 / 成本 / 归属 / 编排方式 */
  channel?: CallChannel | null;
  model_code?: string | null;
  cost_usd?: number | null;
  user_id?: EntityId | null;
  source?: AgentSource | null;
  kind?: GraphKind | null;
  /** P17.C1 嵌套 Observation 字段 */
  parent_id?: string | null;
  observation_type?: ObservationType;
  completion_start_ms?: number | null;
  created_at: string;
}

export type ScoreDataType = 'numeric' | 'categorical' | 'boolean' | 'text';
export type ScoreSource = 'annotation' | 'api' | 'eval' | 'feedback';

export interface ScoreItem {
  id: EntityId;
  call_log_id: string;
  trace_id: string | null;
  name: string;
  value: number | null;
  string_value: string | null;
  data_type: ScoreDataType;
  source: ScoreSource;
  comment: string | null;
  created_at: string;
}

export interface TraceTreeNode {
  id: EntityId;
  request_id: string;
  parent_id: string | null;
  observation_type: ObservationType;
  agent_key: string;
  app_id: string;
  session_id: string | null;
  stream: boolean;
  success: boolean;
  code: number;
  error_message: string | null;
  duration_ms: number;
  completion_start_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  /** 含子节点递归累加的 USD 成本（Agent C C2 聚合 API；未接入时缺省） */
  cost_usd?: number | null;
  created_at: string;
  scores: ScoreItem[];
  children: TraceTreeNode[];
}

export interface SpanRecord {
  name: string;
  start_ms: number;
  end_ms: number;
  status: 'success' | 'failed' | 'running' | string;
  error_class?: string | null;
  error_message?: string | null;
  meta?: Record<string, unknown> | null;
}

export interface CallLogDetail extends CallLogItem {
  spans: SpanRecord[] | null;
  request_payload: Record<string, unknown> | null;
  response_payload: Record<string, unknown> | null;
}

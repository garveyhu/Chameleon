import type { EntityId } from '@/core/types/api';

export type GraphNodeType =
  | 'noop'
  | 'start'
  | 'end'
  | 'llm'
  | 'kb'
  | 'tool'
  | 'if_else';

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

export interface GraphItem {
  id: EntityId;
  graph_key: string;
  name: string;
  description: string | null;
  schema_version: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface GraphDetail extends GraphItem {
  spec: GraphSpec;
}

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

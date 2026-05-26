import type { EntityId } from '@/core/types/api';

export interface AgentItem {
  id: EntityId;
  agent_key: string;
  name: string;
  description: string | null;
  source: 'local' | 'dify' | 'fastgpt' | 'coze' | 'graph' | string;
  provider_id: EntityId | null;
  local_class_path: string | null;
  graph_id: EntityId | null;
  config: Record<string, unknown> | null;
  default_model_id: EntityId | null;
  tags: string[] | null;
  enabled: boolean;
  version: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateAgentRequest {
  agent_key: string;
  name: string;
  description?: string;
  source: 'dify' | 'fastgpt' | 'coze';
  provider_id?: EntityId;
  config?: Record<string, unknown>;
  tags?: string[];
}

export interface LinkedKbItem {
  id: EntityId;
  kb_key: string;
  name: string;
  description: string | null;
  embedding_model: string;
  embedding_dim: number;
}

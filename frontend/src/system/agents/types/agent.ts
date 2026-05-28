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
  /** 关联工作流形态：chatflow / workflow（仅 source='graph' 有值），用于推导编排方式 */
  graph_kind: 'chatflow' | 'workflow' | null;
  config: Record<string, unknown> | null;
  default_model_id: EntityId | null;
  tags: string[] | null;
  enabled: boolean;
  version: string | null;
  /** 头像 data URL（null 用默认按类型图标） */
  icon: string | null;
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

export interface ModelSlotItem {
  name: string;
  label: string;
  optional: boolean;
  locked: boolean;
  default: string | null;
  bound_code: string | null;
}

export interface ConfiguredModelItem {
  code: string;
  label: string;
}

export interface AgentModelSlots {
  slots: ModelSlotItem[];
  models: ConfiguredModelItem[];
}

export interface ConfigOptionItem {
  key: string;
  label: string;
  type: 'string' | 'number' | 'boolean' | 'select' | string;
  choices: string[] | null;
  default: unknown;
  required: boolean;
}

export interface AgentConfigSchema {
  options: ConfigOptionItem[];
  values: Record<string, unknown>;
}

/** 应用级 API 密钥（scope_type='app'，scope_ref = agent_key） */
export interface AgentApiKey {
  id: EntityId;
  name: string;
  key_prefix: string;
  /** 明文 key（留存，可重复复制；老数据为 null，只能看前缀） */
  plain_key: string | null;
  scope_type: string;
  scope_ref: string | null;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

/** 单应用调用概览（监测 tab） */
export interface AgentOverview {
  window_hours: number;
  total_calls: number;
  /** 0~1 */
  success_rate: number;
  total_tokens: number;
  total_cost_usd: number;
  avg_duration_ms: number;
  prev_total_calls: number;
}

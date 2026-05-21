export interface AgentItem {
  id: number;
  agent_key: string;
  name: string;
  description: string | null;
  source: 'local' | 'dify' | 'fastgpt' | 'coze' | string;
  provider_id: number | null;
  local_class_path: string | null;
  config: Record<string, unknown> | null;
  default_model_id: number | null;
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
  provider_id?: number;
  config?: Record<string, unknown>;
  tags?: string[];
}

export interface EmbedConfigItem {
  id: number;
  embed_key: string;
  name: string;
  description: string | null;
  agent_id: number;
  app_id: number;
  allowed_origins: string[] | null;
  ui_config: Record<string, unknown> | null;
  behavior: Record<string, unknown> | null;
  enabled: boolean;
  created_by_user_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface CreateEmbedConfigRequest {
  name: string;
  description?: string;
  agent_id: number;
  app_id: number;
  allowed_origins?: string[];
  ui_config?: Record<string, unknown>;
  behavior?: Record<string, unknown>;
}

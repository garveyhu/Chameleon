import type { EntityId } from '@/core/types/api';
export interface EmbedConfigItem {
  id: EntityId;
  embed_key: string;
  name: string;
  description: string | null;
  agent_id: EntityId;
  app_id: EntityId;
  allowed_origins: string[] | null;
  ui_config: Record<string, unknown> | null;
  behavior: Record<string, unknown> | null;
  enabled: boolean;
  created_by_user_id: EntityId | null;
  created_at: string;
  updated_at: string;
}

export interface CreateEmbedConfigRequest {
  name: string;
  description?: string;
  agent_id: EntityId;
  app_id: EntityId;
  allowed_origins?: string[];
  ui_config?: Record<string, unknown>;
  behavior?: Record<string, unknown>;
}

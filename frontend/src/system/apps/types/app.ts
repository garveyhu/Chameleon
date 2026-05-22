import type { EntityId } from '@/core/types/api';
export interface AppItem {
  id: EntityId;
  app_key: string;
  name: string;
  description: string | null;
  status: 'active' | 'suspended';
  owner_user_id: number | null;
  meta: Record<string, unknown> | null;
  qpm_limit: number | null;
  qpd_limit: number | null;
  created_at: string;
  updated_at: string;
}

export interface CreateAppRequest {
  app_key: string;
  name: string;
  description?: string;
  qpm_limit?: number;
  qpd_limit?: number;
}

export interface ApiKeyItem {
  id: EntityId;
  app_id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  description: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface CreateApiKeyRequest {
  app_id: string;
  name: string;
  scopes?: string[];
  description?: string;
}

export interface ApiKeyCreated extends ApiKeyItem {
  plain_key: string; // 仅一次回显
}

import type { EntityId } from '@/core/types/api';

export interface ModelCapabilities {
  vision?: boolean;
  tool_call?: boolean;
  json_mode?: boolean;
  context_window?: number;
}

export interface ModelItem {
  id: EntityId;
  provider_id: EntityId;
  provider_code: string | null;
  code: string;
  kind: 'chat' | 'embedding' | 'rerank';
  dim: number | null;
  defaults: Record<string, unknown> | null;
  upstream_name: string | null;
  capabilities: ModelCapabilities | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateModelRequest {
  provider_id: EntityId;
  code: string;
  kind: 'chat' | 'embedding' | 'rerank';
  dim?: number;
  defaults?: Record<string, unknown>;
  upstream_name?: string;
  capabilities?: ModelCapabilities;
}

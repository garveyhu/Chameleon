import type { EntityId } from '@/core/types/api';
export interface ModelItem {
  id: EntityId;
  provider_id: EntityId;
  provider_code: string | null;
  code: string;
  kind: 'chat' | 'embedding';
  dim: number | null;
  defaults: Record<string, unknown> | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateModelRequest {
  provider_id: EntityId;
  code: string;
  kind: 'chat' | 'embedding';
  dim?: number;
  defaults?: Record<string, unknown>;
}

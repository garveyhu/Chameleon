import type { EntityId } from '@/core/types/api';

export interface AbilityItem {
  id: EntityId;
  group_id: EntityId | null;
  model_code: string;
  channel_id: EntityId;
  channel_name: string | null;
  provider_code: string | null;
  priority: number;
  weight: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateAbilityRequest {
  group_id?: EntityId | null;
  model_code: string;
  channel_id: EntityId;
  priority?: number;
  weight?: number;
}

export interface UpdateAbilityRequest {
  priority?: number;
  weight?: number;
  enabled?: boolean;
}

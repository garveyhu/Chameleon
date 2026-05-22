import { get, post } from '@/core/lib/request';
import type { EntityId } from '@/core/types/api';
import type {
  AbilityItem,
  CreateAbilityRequest,
  UpdateAbilityRequest,
} from '@/system/abilities/types/ability';

export const abilityApi = {
  list: (params?: {
    model_code?: string;
    group_id?: number;
    channel_id?: EntityId;
  }) => get<AbilityItem[]>('/v1/admin/abilities', { params }),
  create: (req: CreateAbilityRequest) => post<AbilityItem>('/v1/admin/abilities', req),
  update: (id: EntityId, req: UpdateAbilityRequest) =>
    post<AbilityItem>(`/v1/admin/abilities/${id}/update`, req),
  delete: (id: EntityId) => post<void>(`/v1/admin/abilities/${id}/delete`),
};

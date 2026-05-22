import { get, post } from '@/core/lib/request';
import type { EntityId } from '@/core/types/api';
import type {
  ChannelItem,
  CreateChannelRequest,
  UpdateChannelRequest,
} from '@/system/channels/types/channel';

export const channelApi = {
  list: (params?: { provider_id?: EntityId; status?: string }) =>
    get<ChannelItem[]>('/v1/admin/channels', { params }),
  get: (id: EntityId) => get<ChannelItem>(`/v1/admin/channels/${id}`),
  create: (req: CreateChannelRequest) => post<ChannelItem>('/v1/admin/channels', req),
  update: (id: EntityId, req: UpdateChannelRequest) =>
    post<ChannelItem>(`/v1/admin/channels/${id}/update`, req),
  delete: (id: EntityId) => post<void>(`/v1/admin/channels/${id}/delete`),
};

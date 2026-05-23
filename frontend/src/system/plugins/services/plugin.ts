import { get, post } from '@/core/lib/request';
import type { EntityId } from '@/core/types/api';
import type {
  InstallPluginPayload,
  PluginActionResult,
  PluginInstanceItem,
} from '@/system/plugins/types/plugin';

export const pluginApi = {
  list: () => get<PluginInstanceItem[]>('/v1/admin/plugins'),

  get: (id: EntityId) =>
    get<PluginInstanceItem>(`/v1/admin/plugins/${id}`),

  install: (payload: InstallPluginPayload) =>
    post<PluginInstanceItem>('/v1/admin/plugins/install', payload),

  enable: (id: EntityId) =>
    post<PluginActionResult>(`/v1/admin/plugins/${id}/enable`, {}),

  disable: (id: EntityId) =>
    post<PluginActionResult>(`/v1/admin/plugins/${id}/disable`, {}),

  reload: (id: EntityId) =>
    post<PluginActionResult>(`/v1/admin/plugins/${id}/reload`, {}),

  uninstall: (id: EntityId) =>
    post<null>(`/v1/admin/plugins/${id}/uninstall`, {}),

  updateConfig: (id: EntityId, config: Record<string, unknown>) =>
    post<PluginInstanceItem>(`/v1/admin/plugins/${id}/config`, { config }),
};

import { get, post } from '@/core/lib/request';
import type { EntityId } from '@/core/types/api';
import type {
  AgentApiKey,
  AgentConfigSchema,
  AgentItem,
  AgentModelSlots,
  AgentOverview,
  CreateAgentRequest,
  LinkedKbItem,
} from '@/system/agents/types/agent';

interface InvokeResult {
  answer: string;
  session_id: string;
  request_id: string | null;
}

export const agentApi = {
  list: (params?: { source?: string; enabled?: boolean }) =>
    get<AgentItem[]>('/v1/admin/agents', { params }),
  get: (id: EntityId) => get<AgentItem>(`/v1/admin/agents/${id}`),
  create: (req: CreateAgentRequest) => post<AgentItem>('/v1/admin/agents', req),
  update: (id: EntityId, req: Partial<CreateAgentRequest> & { icon?: string | null }) =>
    post<AgentItem>(`/v1/admin/agents/${id}/update`, req),
  delete: (id: EntityId) => post<void>(`/v1/admin/agents/${id}/delete`),
  enable: (id: EntityId) => post<AgentItem>(`/v1/admin/agents/${id}/enable`),
  disable: (id: EntityId) => post<AgentItem>(`/v1/admin/agents/${id}/disable`),
  test: (id: EntityId, input: string) =>
    post<InvokeResult>(`/v1/admin/agents/${id}/test`, { input }),

  linkedKbs: (id: EntityId) => get<LinkedKbItem[]>(`/v1/admin/agents/${id}/linked-kbs`),
  updateLinkedKbs: (id: EntityId, kbIds: EntityId[]) =>
    post<LinkedKbItem[]>(`/v1/admin/agents/${id}/linked-kbs/update`, {
      kb_ids: kbIds,
    }),

  modelSlots: (id: EntityId) => get<AgentModelSlots>(`/v1/admin/agents/${id}/model-slots`),
  updateModelBindings: (id: EntityId, bindings: Record<string, string>) =>
    post<AgentModelSlots>(`/v1/admin/agents/${id}/model-bindings/update`, {
      bindings,
    }),

  configSchema: (id: EntityId) => get<AgentConfigSchema>(`/v1/admin/agents/${id}/config-schema`),
  updateConfig: (id: EntityId, values: Record<string, unknown>) =>
    post<AgentConfigSchema>(`/v1/admin/agents/${id}/config/update`, { values }),

  /** 应用级密钥：列未吊销 */
  listApiKeys: (id: EntityId) => get<AgentApiKey[]>(`/v1/admin/agents/${id}/api-keys`),
  /** 应用级密钥：新建（明文仅此响应可见） */
  createApiKey: (id: EntityId, name: string) =>
    post<AgentApiKey>(`/v1/admin/agents/${id}/api-keys`, { name }),
  /** 应用级密钥：吊销 */
  revokeApiKey: (id: EntityId, keyId: EntityId) =>
    post<AgentApiKey>(`/v1/admin/agents/${id}/api-keys/${keyId}/revoke`),

  /** 调用概览（监测）：按时间窗聚合 */
  overview: (id: EntityId, hours: number) =>
    get<AgentOverview>(`/v1/admin/agents/${id}/overview`, { params: { hours } }),
};

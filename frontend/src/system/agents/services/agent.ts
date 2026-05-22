import { get, post } from '@/core/lib/request';
import type { EntityId } from '@/core/types/api';
import type {
  AgentItem,
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
  update: (id: EntityId, req: Partial<CreateAgentRequest>) =>
    post<AgentItem>(`/v1/admin/agents/${id}/update`, req),
  delete: (id: EntityId) => post<void>(`/v1/admin/agents/${id}/delete`),
  enable: (id: EntityId) => post<AgentItem>(`/v1/admin/agents/${id}/enable`),
  disable: (id: EntityId) => post<AgentItem>(`/v1/admin/agents/${id}/disable`),
  test: (id: EntityId, input: string) =>
    post<InvokeResult>(`/v1/admin/agents/${id}/test`, { input }),

  linkedKbs: (id: EntityId) =>
    get<LinkedKbItem[]>(`/v1/admin/agents/${id}/linked-kbs`),
  updateLinkedKbs: (id: EntityId, kbIds: EntityId[]) =>
    post<LinkedKbItem[]>(`/v1/admin/agents/${id}/linked-kbs/update`, {
      kb_ids: kbIds,
    }),
};

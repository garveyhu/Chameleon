import { get, post } from '@/core/lib/request';
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
  get: (id: number) => get<AgentItem>(`/v1/admin/agents/${id}`),
  create: (req: CreateAgentRequest) => post<AgentItem>('/v1/admin/agents', req),
  update: (id: number, req: Partial<CreateAgentRequest>) =>
    post<AgentItem>(`/v1/admin/agents/${id}/update`, req),
  delete: (id: number) => post<void>(`/v1/admin/agents/${id}/delete`),
  enable: (id: number) => post<AgentItem>(`/v1/admin/agents/${id}/enable`),
  disable: (id: number) => post<AgentItem>(`/v1/admin/agents/${id}/disable`),
  test: (id: number, input: string) =>
    post<InvokeResult>(`/v1/admin/agents/${id}/test`, { input }),

  linkedKbs: (id: number) =>
    get<LinkedKbItem[]>(`/v1/admin/agents/${id}/linked-kbs`),
  updateLinkedKbs: (id: number, kbIds: number[]) =>
    post<LinkedKbItem[]>(`/v1/admin/agents/${id}/linked-kbs/update`, {
      kb_ids: kbIds,
    }),
};

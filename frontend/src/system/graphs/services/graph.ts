import { get, post } from '@/core/lib/request';
import type { EntityId } from '@/core/types/api';
import type {
  GraphDetail,
  GraphItem,
  GraphSpec,
  TestRunResult,
} from '@/system/graphs/types/graph';

export interface CreateGraphPayload {
  graph_key: string;
  name: string;
  description?: string | null;
  spec: GraphSpec;
}

export interface UpdateGraphPayload {
  name?: string;
  description?: string | null;
  spec?: GraphSpec;
  enabled?: boolean;
}

export const graphApi = {
  list: () => get<GraphItem[]>('/v1/admin/graphs'),

  get: (id: EntityId) => get<GraphDetail>(`/v1/admin/graphs/${id}`),

  create: (payload: CreateGraphPayload) =>
    post<GraphDetail>('/v1/admin/graphs', payload),

  update: (id: EntityId, payload: UpdateGraphPayload) =>
    post<GraphDetail>(`/v1/admin/graphs/${id}/update`, payload),

  delete: (id: EntityId) => post<null>(`/v1/admin/graphs/${id}/delete`, {}),

  testRun: (id: EntityId, input: Record<string, unknown> = {}) =>
    post<TestRunResult>(`/v1/admin/graphs/${id}/test-run`, { input }),
};

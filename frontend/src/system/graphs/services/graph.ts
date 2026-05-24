import { get, post } from '@/core/lib/request';
import { streamSSE } from '@/core/lib/sse';
import type { EntityId } from '@/core/types/api';
import type {
  GraphChatChunk,
  GraphDetail,
  GraphItem,
  GraphRunDetail,
  GraphRunItem,
  GraphSpec,
  GraphStreamChunk,
  TestRunResult,
} from '@/system/graphs/types/graph';

export interface GraphChatTurn {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

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

  /** 流式 Test Run（不落库）：边执行边推 graph.node.* 事件，节点状态实时回投 canvas */
  testRunStream: (
    id: EntityId,
    input: Record<string, unknown>,
    opts: { signal?: AbortSignal; onChunk: (chunk: GraphStreamChunk) => void },
  ): Promise<void> =>
    streamSSE<GraphStreamChunk>(`/v1/admin/graphs/${id}/test-run/stream`, {
      body: { input },
      signal: opts.signal,
      onChunk: opts.onChunk,
    }),

  /** 正式跑（持久化 + 写 call_logs，串到 trace tree） */
  run: (id: EntityId, input: Record<string, unknown> = {}) =>
    post<GraphRunDetail>(`/v1/admin/graphs/${id}/run`, { input }),

  /** P22.3：发布 draft → freeze published_spec；published_version += 1 */
  publish: (id: EntityId) =>
    post<GraphDetail>(`/v1/admin/graphs/${id}/publish`, {}),

  /** 发布并暴露成可对话 agent（source='graph'），走统一 agent 端点 */
  publishAsAgent: (id: EntityId) =>
    post<{ agent_key: string; agent_id: EntityId }>(
      `/v1/admin/graphs/${id}/publish-as-agent`,
      {},
    ),

  /** 对话式调试当前 draft（把 graph 当可对话 agent 多轮跑，临时会话不落库） */
  chatStream: (
    id: EntityId,
    body: { message: string; history: GraphChatTurn[] },
    opts: { signal?: AbortSignal; onChunk: (chunk: GraphChatChunk) => void },
  ): Promise<void> =>
    streamSSE<GraphChatChunk>(`/v1/admin/graphs/${id}/chat/stream`, {
      body,
      signal: opts.signal,
      onChunk: opts.onChunk,
    }),

  listRuns: (id: EntityId) =>
    get<GraphRunItem[]>(`/v1/admin/graphs/${id}/runs`),
};

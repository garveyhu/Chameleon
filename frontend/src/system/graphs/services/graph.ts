import { get, post } from '@/core/lib/request';
import { streamSSE } from '@/core/lib/sse';
import type { EntityId, PageResult } from '@/core/types/api';
import type {
  AgentApiKey,
  AgentApiKeyCreated,
  GraphChatChunk,
  GraphDetail,
  GraphItem,
  GraphKind,
  GraphRunDetail,
  GraphRunItem,
  GraphSpec,
  GraphStreamChunk,
  TestRunResult,
  WebAppInfo,
} from '@/system/graphs/types/graph';

export interface GraphChatTurn {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface CreateGraphPayload {
  graph_key: string;
  name: string;
  description?: string | null;
  kind?: GraphKind;
  spec: GraphSpec;
}

export interface UpdateGraphPayload {
  name?: string;
  description?: string | null;
  kind?: GraphKind;
  spec?: GraphSpec;
  enabled?: boolean;
}

export const graphApi = {
  list: () => get<GraphItem[]>('/v1/admin/graphs'),

  get: (id: EntityId) => get<GraphDetail>(`/v1/admin/graphs/${id}`),

  create: (payload: CreateGraphPayload) => post<GraphDetail>('/v1/admin/graphs', payload),

  /** A4：自然语言描述 → LLM 生成并创建工作流图 */
  generate: (payload: { description: string; graph_key: string; name: string }) =>
    post<GraphDetail>('/v1/admin/graphs/generate', payload),

  /** A2：基于一轮问答生成建议追问 */
  suggestFollowups: (payload: { question: string; answer: string }) =>
    post<string[]>('/v1/admin/graphs/suggest-followups', payload),

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
  publish: (id: EntityId) => post<GraphDetail>(`/v1/admin/graphs/${id}/publish`, {}),

  /** 发布并暴露成可对话 agent（source='graph'），走统一 agent 端点 */
  publishAsAgent: (id: EntityId) =>
    post<{ agent_key: string; agent_id: EntityId }>(`/v1/admin/graphs/${id}/publish-as-agent`, {}),

  /** 确保工作流有公开 Web App（embed），返回 embed_key（公开页 /embed/{key}） */
  ensureWebApp: (id: EntityId) => post<WebAppInfo>(`/v1/admin/graphs/${id}/web-app`, {}),

  /** Web App 设置：写回展示 / 行为配置 */
  updateWebApp: (
    id: EntityId,
    payload: {
      name?: string;
      description?: string | null;
      ui_config?: Record<string, unknown>;
      behavior?: Record<string, unknown>;
      enabled?: boolean;
    },
  ) => post<WebAppInfo>(`/v1/admin/graphs/${id}/web-app/update`, payload),

  /** 对话式调试当前 draft（把 graph 当可对话 agent 多轮跑，临时会话不落库） */
  chatStream: (
    id: EntityId,
    body: {
      message: string;
      history: GraphChatTurn[];
      conversation_vars?: Record<string, unknown>;
    },
    opts: { signal?: AbortSignal; onChunk: (chunk: GraphChatChunk) => void },
  ): Promise<void> =>
    streamSSE<GraphChatChunk>(`/v1/admin/graphs/${id}/chat/stream`, {
      body,
      signal: opts.signal,
      onChunk: opts.onChunk,
    }),

  /** 分页列运行记录（最新在前），支持状态 / 会话 / 时间范围筛选 */
  listRuns: (
    id: EntityId,
    params?: {
      page?: number;
      page_size?: number;
      status?: string;
      session_id?: string;
      since?: string;
      until?: string;
    },
  ) => get<PageResult<GraphRunItem>>(`/v1/admin/graphs/${id}/runs`, { params }),

  /** 单次运行详情（含逐节点执行 node_runs） */
  getRun: (runId: EntityId) => get<GraphRunDetail>(`/v1/admin/graphs/runs/${runId}`),

  /** 智能体级密钥：列未吊销 */
  listAgentKeys: (graphId: EntityId) => get<AgentApiKey[]>(`/v1/admin/graphs/${graphId}/api-keys`),

  /** 智能体级密钥：新建（明文仅此响应可见） */
  createAgentKey: (graphId: EntityId, name: string) =>
    post<AgentApiKeyCreated>(`/v1/admin/graphs/${graphId}/api-keys`, { name }),

  /** 智能体级密钥：吊销 */
  revokeAgentKey: (graphId: EntityId, keyId: EntityId) =>
    post<AgentApiKey>(`/v1/admin/graphs/${graphId}/api-keys/${keyId}/revoke`, {}),
};

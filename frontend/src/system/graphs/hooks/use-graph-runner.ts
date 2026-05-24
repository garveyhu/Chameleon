/** useGraphRunner —— 编辑器调试运行状态机
 *
 * 职责：把 Test Run（流式）/ Run（持久化）收口成一个状态机：
 * - 跑前若画布有未保存改动，先 await save()（不再静默跑服务端旧 spec）
 * - Test Run 走 SSE：逐 chunk 把节点状态投到 nodeRuns（canvas 据此染色 + inspector 看结果）
 * - Run 走持久化端点：拿最终 output / status，写 call_logs（trace tree 可见）
 *
 * run state 留在本 hook（非全局 store）：随编辑器实例生灭，切图自动重置。
 */

import { useCallback, useEffect, useReducer, useRef } from 'react';

import type { EntityId } from '@/core/types/api';
import { graphApi } from '@/system/graphs/services/graph';
import type {
  GraphStreamChunk,
  NodeRunView,
} from '@/system/graphs/types/graph';

export type RunPhase = 'idle' | 'running' | 'success' | 'failed';

export interface GraphRunState {
  phase: RunPhase;
  /** 本次运行是否走的持久化端点 */
  persisted: boolean;
  nodeRuns: Record<string, NodeRunView>;
  finalOutput: unknown;
  runError: { type: string; message: string } | null;
  durationMs: number | null;
  nodeCount: number | null;
}

type Action =
  | { kind: 'begin'; persisted: boolean }
  | { kind: 'node'; nodeId: string; patch: Partial<NodeRunView> }
  | { kind: 'delta'; nodeId: string; text: string }
  | {
      kind: 'end';
      status: 'success' | 'failed';
      output?: unknown;
      error?: { type: string; message: string } | null;
      durationMs?: number | null;
      nodeCount?: number | null;
    }
  | { kind: 'reset' };

const INITIAL: GraphRunState = {
  phase: 'idle',
  persisted: false,
  nodeRuns: {},
  finalOutput: null,
  runError: null,
  durationMs: null,
  nodeCount: null,
};

function reducer(state: GraphRunState, action: Action): GraphRunState {
  switch (action.kind) {
    case 'begin':
      return {
        ...INITIAL,
        phase: 'running',
        persisted: action.persisted,
      };
    case 'node': {
      const prev = state.nodeRuns[action.nodeId];
      return {
        ...state,
        nodeRuns: {
          ...state.nodeRuns,
          [action.nodeId]: {
            ...prev,
            ...action.patch,
            status: action.patch.status ?? prev?.status ?? 'running',
          },
        },
      };
    }
    case 'delta': {
      const prev = state.nodeRuns[action.nodeId];
      return {
        ...state,
        nodeRuns: {
          ...state.nodeRuns,
          [action.nodeId]: {
            ...prev,
            streamText: (prev?.streamText ?? '') + action.text,
            status: prev?.status ?? 'running',
          },
        },
      };
    }
    case 'end':
      return {
        ...state,
        phase: action.status,
        finalOutput: action.output ?? state.finalOutput,
        runError: action.error ?? null,
        durationMs: action.durationMs ?? state.durationMs,
        nodeCount: action.nodeCount ?? state.nodeCount,
      };
    case 'reset':
      return INITIAL;
    default:
      return state;
  }
}

export interface UseGraphRunnerArgs {
  graphId: EntityId;
  /** 画布是否有未保存改动 */
  isDirty: boolean;
  /** 保存当前画布草稿；失败应 reject */
  save: () => Promise<void>;
}

export function useGraphRunner({ graphId, isDirty, save }: UseGraphRunnerArgs) {
  const [state, dispatch] = useReducer(reducer, INITIAL);
  const abortRef = useRef<AbortController | null>(null);

  // 切图：中断在途流 + 重置运行态
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, [graphId]);
  useEffect(() => {
    dispatch({ kind: 'reset' });
  }, [graphId]);

  const onChunk = useCallback((chunk: GraphStreamChunk) => {
    if ('graph.node.started' in chunk) {
      const p = chunk['graph.node.started'];
      dispatch({ kind: 'node', nodeId: p.node_id, patch: { status: 'running' } });
    } else if ('graph.node.delta' in chunk) {
      const p = chunk['graph.node.delta'];
      dispatch({ kind: 'delta', nodeId: p.node_id, text: p.delta });
    } else if ('graph.node.finished' in chunk) {
      const p = chunk['graph.node.finished'];
      dispatch({
        kind: 'node',
        nodeId: p.node_id,
        patch: {
          status: 'success',
          output: p.output,
          duration_ms: p.duration_ms ?? undefined,
        },
      });
    } else if ('graph.node.failed' in chunk) {
      const p = chunk['graph.node.failed'];
      dispatch({
        kind: 'node',
        nodeId: p.node_id,
        patch: {
          status: 'failed',
          error: p.error ?? null,
          duration_ms: p.duration_ms ?? undefined,
        },
      });
    } else if ('graph.finished' in chunk) {
      const p = chunk['graph.finished'];
      dispatch({
        kind: 'end',
        status: p.status === 'success' ? 'success' : 'failed',
        output: p.output,
        error: p.error ?? null,
        durationMs: p.duration_ms ?? null,
        nodeCount: p.node_count ?? null,
      });
    }
  }, []);

  /** Test Run（流式调试，不落库）。返回 promise；调用方负责 toast。 */
  const runTest = useCallback(
    async (input: Record<string, unknown>) => {
      if (isDirty) await save();
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      dispatch({ kind: 'begin', persisted: false });
      try {
        await graphApi.testRunStream(graphId, input, {
          signal: ctrl.signal,
          onChunk,
        });
      } catch (e) {
        if (ctrl.signal.aborted) return;
        dispatch({
          kind: 'end',
          status: 'failed',
          error: { type: 'StreamError', message: (e as Error).message },
        });
        throw e;
      }
    },
    [graphId, isDirty, save, onChunk],
  );

  /** Run（持久化执行，写 call_logs）。非流式：拿最终 output / status。 */
  const runPersist = useCallback(
    async (input: Record<string, unknown>) => {
      if (isDirty) await save();
      dispatch({ kind: 'begin', persisted: true });
      try {
        const detail = await graphApi.run(graphId, input);
        dispatch({
          kind: 'end',
          status: detail.status === 'success' ? 'success' : 'failed',
          output: detail.output,
          error: detail.error ?? null,
          durationMs: detail.duration_ms ?? null,
          nodeCount: detail.node_count ?? null,
        });
        return detail;
      } catch (e) {
        dispatch({
          kind: 'end',
          status: 'failed',
          error: { type: 'RunError', message: (e as Error).message },
        });
        throw e;
      }
    },
    [graphId, isDirty, save],
  );

  return { ...state, runTest, runPersist };
}

export type GraphRunner = ReturnType<typeof useGraphRunner>;

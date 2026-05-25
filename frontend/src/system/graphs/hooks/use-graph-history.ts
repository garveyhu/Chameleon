/** 画布撤销/重做历史栈 —— React Flow 不自带，自己维护 nodes/edges 快照
 *
 * 用法：在「会改变画布」的操作前调 commit()（快照改前状态）；undo/redo 还原。
 * - 快照存数组浅拷贝即可：React Flow 改动时生成新数组/新节点对象，旧快照不被原地改。
 * - 还原走 setNodes/setEdges（程序化 set 不触发 onNodesChange，不会回灌历史）。
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import type { Edge, Node as RFNode } from '@xyflow/react';

import type { GraphNodeData } from '@/system/graphs/components/nodes/graph-node';

type RFN = RFNode<GraphNodeData>;
interface Snapshot {
  nodes: RFN[];
  edges: Edge[];
}

const MAX_HISTORY = 200;

interface Params {
  nodes: RFN[];
  edges: Edge[];
  setNodes: (nodes: RFN[]) => void;
  setEdges: (edges: Edge[]) => void;
  /** 还原后回调（置脏） */
  onApplied: () => void;
}

export interface GraphHistory {
  /** 在改动前调用：把当前 nodes/edges 压入撤销栈 */
  commit: () => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  /** 重挂另一张图时清空历史 */
  reset: () => void;
}

export function useGraphHistory({
  nodes,
  edges,
  setNodes,
  setEdges,
  onApplied,
}: Params): GraphHistory {
  // 始终持最新 nodes/edges 引用，供 commit/undo 读取改前快照（在 effect 里同步，避免 render 期写 ref）
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  useEffect(() => {
    nodesRef.current = nodes;
    edgesRef.current = edges;
  }, [nodes, edges]);

  const past = useRef<Snapshot[]>([]);
  const future = useRef<Snapshot[]>([]);
  const restoring = useRef(false);
  // canUndo/canRedo 走 state（不在 render 期读 ref）
  const [flags, setFlags] = useState({ canUndo: false, canRedo: false });
  const sync = useCallback(() => {
    setFlags({
      canUndo: past.current.length > 0,
      canRedo: future.current.length > 0,
    });
  }, []);

  const commit = useCallback(() => {
    if (restoring.current) return;
    past.current.push({ nodes: [...nodesRef.current], edges: [...edgesRef.current] });
    if (past.current.length > MAX_HISTORY) past.current.shift();
    if (future.current.length) future.current = [];
    sync();
  }, [sync]);

  const undo = useCallback(() => {
    const prev = past.current.pop();
    if (!prev) return;
    future.current.push({
      nodes: [...nodesRef.current],
      edges: [...edgesRef.current],
    });
    restoring.current = true;
    setNodes(prev.nodes);
    setEdges(prev.edges);
    onApplied();
    requestAnimationFrame(() => {
      restoring.current = false;
    });
    sync();
  }, [setNodes, setEdges, onApplied, sync]);

  const redo = useCallback(() => {
    const next = future.current.pop();
    if (!next) return;
    past.current.push({
      nodes: [...nodesRef.current],
      edges: [...edgesRef.current],
    });
    restoring.current = true;
    setNodes(next.nodes);
    setEdges(next.edges);
    onApplied();
    requestAnimationFrame(() => {
      restoring.current = false;
    });
    sync();
  }, [setNodes, setEdges, onApplied, sync]);

  const reset = useCallback(() => {
    past.current = [];
    future.current = [];
    sync();
  }, [sync]);

  return {
    commit,
    undo,
    redo,
    canUndo: flags.canUndo,
    canRedo: flags.canRedo,
    reset,
  };
}

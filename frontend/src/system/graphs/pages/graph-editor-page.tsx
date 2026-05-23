/** GraphEditor —— React Flow canvas + 左 palette + 右 inspector + 顶 toolbar
 *
 * 状态约定：本地 nodes/edges 用 React Flow 的"扁平"结构；保存时映射回后端 GraphSpec。
 * 双向映射：
 *   后端 spec.nodes[].position {x,y}  ↔  React Flow node.position
 *   后端 spec.edges[].source_handle ↔  React Flow edge.sourceHandle
 *   后端 spec.nodes[].data        ↔  React Flow node.data._spec  (避免和 GraphNode 渲染数据冲突)
 *
 * 跑 test-run 后把每个 node_run.status 投影回 React Flow node.data.runStatus，边框变色。
 */

import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from '@xyflow/react';
import type {
  Connection,
  Edge,
  Node as RFNode,
  ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, History, Play, Save, Zap } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { Spinner } from '@/core/components/common/spinner';
import { Button } from '@/core/components/ui/button';
import { toast } from '@/core/lib/toast';
import { NodeInspector } from '@/system/graphs/components/node-inspector';
import { NodePalette } from '@/system/graphs/components/node-palette';
import { RunsPanel } from '@/system/graphs/components/runs-panel';
import { GraphNode } from '@/system/graphs/components/nodes/graph-node';
import type { GraphNodeData } from '@/system/graphs/components/nodes/graph-node';
import { graphApi } from '@/system/graphs/services/graph';
import type {
  EdgeSpec,
  GraphDetail,
  GraphNodeType,
  GraphRunItem,
  GraphSpec,
  NodeSpec,
  TestRunResult,
} from '@/system/graphs/types/graph';

const NODE_TYPES = {
  graphNode: GraphNode,
} as const;

export const GraphEditorPage = () => {
  return (
    <ReactFlowProvider>
      <EditorInner />
    </ReactFlowProvider>
  );
};

const EditorInner = () => {
  const { id } = useParams<{ id: string }>();
  const graphId = id ?? '';  // 雪花 ID 超 Number.MAX_SAFE_INTEGER，必须保字符串
  const nav = useNavigate();
  const qc = useQueryClient();

  const detailQ = useQuery({
    queryKey: ['graph', graphId],
    queryFn: () => graphApi.get(graphId),
    enabled: !!graphId,
  });

  if (detailQ.isLoading || !detailQ.data) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    );
  }

  return <EditorBody graph={detailQ.data} onReturn={() => nav('/graphs')} onSaved={() => qc.invalidateQueries({ queryKey: ['graph', graphId] })} />;
};

interface EditorBodyProps {
  graph: GraphDetail;
  onReturn: () => void;
  onSaved: () => void;
}

const EditorBody = ({ graph, onReturn, onSaved }: EditorBodyProps) => {
  const [nodes, setNodes, onNodesChange] = useNodesState<RFNode<GraphNodeData>>(
    [],
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<TestRunResult | null>(null);
  const idSeqRef = useRef(0);
  const rfWrapperRef = useRef<HTMLDivElement>(null);
  const rfInstance = useReactFlow();

  // 初始 mount：把后端 spec 投到 React Flow
  useEffect(() => {
    const { rfNodes, rfEdges } = specToRf(graph.spec);
    setNodes(rfNodes);
    setEdges(rfEdges);
    idSeqRef.current = Math.max(
      0,
      ...graph.spec.nodes
        .map(n => n.id)
        .filter(id => /^n\d+$/.test(id))
        .map(id => Number(id.slice(1))),
    );
  }, [graph.id, graph.spec, setEdges, setNodes]);

  const onConnect = useCallback(
    (conn: Connection) => {
      setEdges(es =>
        addEdge(
          {
            ...conn,
            id: `e_${conn.source}_${conn.sourceHandle ?? 'out'}_${conn.target}`,
            type: 'smoothstep',
          },
          es,
        ),
      );
    },
    [setEdges],
  );

  const nextNodeId = () => {
    idSeqRef.current += 1;
    return `n${idSeqRef.current}`;
  };

  const addNode = useCallback(
    (type: GraphNodeType, position?: { x: number; y: number }) => {
      const newId = nextNodeId();
      const pos =
        position ?? rfInstance.screenToFlowPosition({ x: 300, y: 200 });
      const data: GraphNodeData = {
        label: defaultLabel(type, newId),
        nodeType: type,
      };
      // 把后端态藏在 data._spec
      const rfNode: RFNode<GraphNodeData> = {
        id: newId,
        position: pos,
        type: 'graphNode',
        data: { ...data, ...({ _spec: { data: {} } } as any) },
      };
      setNodes(ns => ns.concat(rfNode));
      setSelectedId(newId);
    },
    [rfInstance, setNodes],
  );

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      const type = e.dataTransfer.getData('application/x-graph-node-type') as GraphNodeType;
      if (!type) return;
      const bounds = rfWrapperRef.current?.getBoundingClientRect();
      const point = rfInstance.screenToFlowPosition({
        x: e.clientX - (bounds?.left ?? 0),
        y: e.clientY - (bounds?.top ?? 0),
      });
      addNode(type, point);
    },
    [addNode, rfInstance],
  );

  const onDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  }, []);

  const selectedRfNode = useMemo(
    () => nodes.find(n => n.id === selectedId) ?? null,
    [nodes, selectedId],
  );
  const selectedSpec: NodeSpec | null = useMemo(() => {
    if (!selectedRfNode) return null;
    const stored = (selectedRfNode.data as any)?._spec ?? {};
    return {
      id: selectedRfNode.id,
      type: selectedRfNode.data.nodeType,
      name: selectedRfNode.data.label,
      data: stored.data || {},
      position: selectedRfNode.position,
    };
  }, [selectedRfNode]);

  const updateSelectedSpec = useCallback(
    (next: NodeSpec) => {
      setNodes(ns =>
        ns.map(n => {
          if (n.id !== next.id) return n;
          return {
            ...n,
            data: {
              ...n.data,
              label: next.name || next.id,
              _spec: { data: next.data || {} },
            } as GraphNodeData,
          };
        }),
      );
    },
    [setNodes],
  );

  const deleteSelected = useCallback(() => {
    if (!selectedId) return;
    setNodes(ns => ns.filter(n => n.id !== selectedId));
    setEdges(es => es.filter(e => e.source !== selectedId && e.target !== selectedId));
    setSelectedId(null);
  }, [selectedId, setEdges, setNodes]);

  // ── save & test-run ──────────────────────────────────────

  const saveMut = useMutation({
    mutationFn: () => {
      const spec = rfToSpec(nodes, edges);
      return graphApi.update(graph.id, { spec });
    },
    onSuccess: () => {
      toast.success('已保存');
      onSaved();
    },
    onError: e => toast.error(`保存失败：${(e as Error).message}`),
  });

  const applyTestRunResult = useCallback(
    (r: TestRunResult) => {
      setRunResult(r);
      setNodes(ns =>
        ns.map(n => {
          const nr = r.node_runs.find(x => x.node_id === n.id);
          return {
            ...n,
            data: {
              ...n.data,
              runStatus: nr?.status,
              errorMessage: nr?.error?.message,
            } as GraphNodeData,
          };
        }),
      );
      toast[r.status === 'success' ? 'success' : 'error'](
        r.status === 'success'
          ? `执行成功 · ${r.duration_ms}ms`
          : `执行失败：${r.error?.message || 'unknown'}`,
      );
    },
    [setNodes],
  );

  const testRunMut = useMutation({
    mutationFn: () => graphApi.testRun(graph.id, {}),
    onSuccess: applyTestRunResult,
    onError: e => toast.error(`执行失败：${(e as Error).message}`),
  });

  /** 正式 run：持久化 + 写 call_logs（trace tree drawer 可见） */
  const persistRunMut = useMutation({
    mutationFn: () => graphApi.run(graph.id, {}),
    onSuccess: () => {
      toast.success('已发起持久化执行（trace 写入 call_logs）');
      runsQ.refetch();
    },
    onError: e => toast.error(`执行失败：${(e as Error).message}`),
  });

  const runsQ = useQuery({
    queryKey: ['graph-runs', graph.id],
    queryFn: () => graphApi.listRuns(graph.id),
  });
  const [runsOpen, setRunsOpen] = useState(false);

  // ── render ───────────────────────────────────────────────

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-center justify-between border-b border-stone-200/70 bg-white px-3 py-2">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onReturn}>
            <ChevronLeft className="mr-0.5 h-3.5 w-3.5" />
            返回
          </Button>
          <div className="text-[13px] font-medium text-stone-900">
            {graph.name}
          </div>
          <span className="font-mono text-[11px] text-stone-500">
            ({graph.graph_key})
          </span>
        </div>
        <div className="flex items-center gap-2">
          {runResult && (
            <span
              className={
                runResult.status === 'success'
                  ? 'text-[11px] text-emerald-600'
                  : 'text-[11px] text-rose-600'
              }
            >
              {runResult.status === 'success' ? '✓' : '✗'}{' '}
              {runResult.duration_ms}ms · {runResult.node_runs.length} nodes
            </span>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setRunsOpen(o => !o)}
            title="历史 runs"
          >
            <History className="h-3 w-3" />
            {runsQ.data ? ` ${runsQ.data.length}` : ''}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => testRunMut.mutate()}
            disabled={testRunMut.isPending}
            title="跑一次但不写 call_logs（debug 用）"
          >
            <Play className="mr-1 h-3 w-3" />
            Test Run
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => persistRunMut.mutate()}
            disabled={persistRunMut.isPending}
            title="持久化执行：写 graph_runs + call_logs，trace tree drawer 可见"
          >
            <Zap className="mr-1 h-3 w-3" />
            Run
          </Button>
          <Button
            size="sm"
            onClick={() => saveMut.mutate()}
            disabled={saveMut.isPending}
          >
            <Save className="mr-1 h-3 w-3" />
            保存
          </Button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <NodePalette onAdd={addNode} />

        <div
          ref={rfWrapperRef}
          className="relative min-w-0 flex-1"
          onDrop={onDrop}
          onDragOver={onDragOver}
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_e, n) => setSelectedId(n.id)}
            onPaneClick={() => setSelectedId(null)}
            nodeTypes={NODE_TYPES}
            fitView
            proOptions={{ hideAttribution: true }}
            defaultEdgeOptions={{ type: 'smoothstep' }}
          >
            <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
            <Controls showInteractive={false} />
            <MiniMap pannable zoomable className="!bg-warm-2" />
          </ReactFlow>
        </div>

        {runsOpen ? (
          <RunsPanel
            runs={runsQ.data ?? []}
            loading={runsQ.isLoading}
            onClose={() => setRunsOpen(false)}
          />
        ) : (
          <NodeInspector
            node={selectedSpec}
            onChange={updateSelectedSpec}
            onDelete={deleteSelected}
          />
        )}
      </div>
    </div>
  );
};


// ── 双向映射 ──────────────────────────────────────────────


function specToRf(spec: GraphSpec): {
  rfNodes: RFNode<GraphNodeData>[];
  rfEdges: Edge[];
} {
  const rfNodes: RFNode<GraphNodeData>[] = spec.nodes.map(n => ({
    id: n.id,
    type: 'graphNode',
    position: n.position || { x: 100, y: 100 },
    data: {
      label: n.name || n.id,
      nodeType: n.type,
      ...({ _spec: { data: n.data || {} } } as any),
    } as GraphNodeData,
  }));
  const rfEdges: Edge[] = spec.edges.map(e => ({
    id: e.id,
    source: e.source,
    target: e.target,
    sourceHandle: e.source_handle ?? undefined,
    type: 'smoothstep',
  }));
  return { rfNodes, rfEdges };
}

function rfToSpec(
  nodes: RFNode<GraphNodeData>[],
  edges: Edge[],
): GraphSpec {
  return {
    nodes: nodes.map(n => {
      const stored = (n.data as any)?._spec ?? {};
      return {
        id: n.id,
        type: n.data.nodeType,
        name: n.data.label,
        data: stored.data || {},
        position: { x: n.position.x, y: n.position.y },
      };
    }),
    edges: edges.map<EdgeSpec>(e => ({
      id: e.id,
      source: e.source,
      target: e.target,
      source_handle: (e.sourceHandle as string | null | undefined) ?? null,
    })),
  };
}


function defaultLabel(type: GraphNodeType, id: string): string {
  const t: Partial<Record<GraphNodeType, string>> = {
    llm: 'LLM 调用',
    kb: 'KB 检索',
    tool: '工具',
    if_else: '条件分支',
    end: '终态',
    start: '开始',
    noop: '占位',
  };
  return `${t[type] ?? type} · ${id}`;
}

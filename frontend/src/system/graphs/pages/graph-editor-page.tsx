/** GraphEditor —— React Flow canvas + 左 palette + 右 inspector + 顶 toolbar
 *
 * 状态约定：本地 nodes/edges 用 React Flow 的"扁平"结构；保存时映射回后端 GraphSpec。
 * 双向映射：
 *   后端 spec.nodes[].position {x,y}  ↔  React Flow node.position
 *   后端 spec.edges[].source_handle ↔  React Flow edge.sourceHandle
 *   后端 spec.nodes[].data        ↔  React Flow node.data._spec  (避免和 GraphNode 渲染数据冲突)
 *
 * 调试运行（useGraphRunner）：跑前若 dirty 先自动存草稿；Test Run 走 SSE 实时把
 *   node 状态投到 canvas（边框变色）+ run dialog 逐节点列结果；Run 持久化写 call_logs。
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
  EdgeChange,
  Node as RFNode,
  NodeChange,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, History, Play, Rocket, Save } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { Spinner } from '@/core/components/common/spinner';
import { Button } from '@/core/components/ui/button';
import { confirm } from '@/core/lib/confirm';
import { toast } from '@/core/lib/toast';
import { useWorkflowStore } from '@/core/stores/workflow';
import { NodeInspector } from '@/system/graphs/components/node-inspector';
import { NodePalette } from '@/system/graphs/components/node-palette';
import { RunDialog } from '@/system/graphs/components/run-dialog';
import { RunsPanel } from '@/system/graphs/components/runs-panel';
import { GraphNode } from '@/system/graphs/components/nodes/graph-node';
import type { GraphNodeData } from '@/system/graphs/components/nodes/graph-node';
import { useGraphRunner } from '@/system/graphs/hooks/use-graph-runner';
import { defaultLabel, rfToSpec, specToRf } from '@/system/graphs/lib/rf-spec';
import { graphApi } from '@/system/graphs/services/graph';
import type {
  GraphDetail,
  GraphNodeType,
  NodeSpec,
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
  const graphId = id ?? ''; // 雪花 ID 超 Number.MAX_SAFE_INTEGER，必须保字符串
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

  return (
    <EditorBody
      key={String(detailQ.data.id)}
      graph={detailQ.data}
      onReturn={() => nav('/graphs')}
      onSaved={() => qc.invalidateQueries({ queryKey: ['graph', graphId] })}
    />
  );
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
  const selectedId = useWorkflowStore(s => s.selectedNodeId);
  const setSelectedId = useWorkflowStore(s => s.selectNode);
  const resetWorkflow = useWorkflowStore(s => s.reset);
  const idSeqRef = useRef(0);
  const rfWrapperRef = useRef<HTMLDivElement>(null);
  const rfInstance = useReactFlow();

  const [dirty, setDirty] = useState(false);
  const [runsOpen, setRunsOpen] = useState(false);
  const [runOpen, setRunOpen] = useState(false);

  // 初始 mount：把后端 spec 投到 React Flow（程序化 setNodes 不触发 onNodesChange，不置脏）
  // EditorBody 按 graph.id keyed 重挂，dirty 初值即 false，无需在此重置。
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

  // 切到另一张图时清空选中（store 全局，需主动重置）
  useEffect(() => {
    resetWorkflow();
  }, [graph.id, resetWorkflow]);

  const saveMut = useMutation({
    mutationFn: () => {
      const spec = rfToSpec(nodes, edges);
      return graphApi.update(graph.id, { spec });
    },
    onSuccess: () => {
      setDirty(false);
      onSaved();
    },
  });

  const save = useCallback(async () => {
    await saveMut.mutateAsync();
  }, [saveMut]);

  const runner = useGraphRunner({
    graphId: graph.id,
    isDirty: dirty,
    save,
  });

  // 运行结果回投 canvas：node 边框按 runStatus 染色
  useEffect(() => {
    setNodes(ns =>
      ns.map(n => {
        const rv = runner.nodeRuns[n.id];
        return {
          ...n,
          data: {
            ...n.data,
            runStatus: rv?.status,
            errorMessage: rv?.error?.message,
          } as GraphNodeData,
        };
      }),
    );
  }, [runner.nodeRuns, setNodes]);

  const handleNodesChange = useCallback(
    (changes: NodeChange<RFNode<GraphNodeData>>[]) => {
      onNodesChange(changes);
      if (
        changes.some(
          c =>
            c.type === 'position' ||
            c.type === 'remove' ||
            c.type === 'add' ||
            c.type === 'replace',
        )
      ) {
        setDirty(true);
      }
    },
    [onNodesChange],
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange<Edge>[]) => {
      onEdgesChange(changes);
      if (changes.some(c => c.type === 'remove' || c.type === 'add')) {
        setDirty(true);
      }
    },
    [onEdgesChange],
  );

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
      setDirty(true);
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
      const rfNode: RFNode<GraphNodeData> = {
        id: newId,
        position: pos,
        type: 'graphNode',
        data: { ...data, ...({ _spec: { data: {} } } as object) },
      };
      setNodes(ns => ns.concat(rfNode));
      setSelectedId(newId);
      setDirty(true);
    },
    [rfInstance, setNodes, setSelectedId],
  );

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      const type = e.dataTransfer.getData(
        'application/x-graph-node-type',
      ) as GraphNodeType;
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
    const stored = (selectedRfNode.data as { _spec?: { data?: object } })._spec ?? {};
    return {
      id: selectedRfNode.id,
      type: selectedRfNode.data.nodeType,
      name: selectedRfNode.data.label,
      data: (stored.data as Record<string, unknown>) || {},
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
      setDirty(true);
    },
    [setNodes],
  );

  const deleteSelected = useCallback(() => {
    if (!selectedId) return;
    setNodes(ns => ns.filter(n => n.id !== selectedId));
    setEdges(es =>
      es.filter(e => e.source !== selectedId && e.target !== selectedId),
    );
    setSelectedId(null);
    setDirty(true);
  }, [selectedId, setEdges, setNodes, setSelectedId]);

  const publishMut = useMutation({
    mutationFn: () => graphApi.publish(graph.id),
    onSuccess: detail => {
      toast.success(`已发布 v${detail.published_version}`);
      onSaved();
    },
    onError: e => toast.error(`发布失败：${(e as Error).message}`),
  });

  const runsQ = useQuery({
    queryKey: ['graph-runs', graph.id],
    queryFn: () => graphApi.listRuns(graph.id),
  });

  // run dialog 关闭后刷新 runs 列表（持久化执行可能新增）
  useEffect(() => {
    if (!runOpen && runner.persisted && runner.phase !== 'running') {
      runsQ.refetch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runOpen]);

  const nodeMeta = useMemo(
    () =>
      nodes.map(n => ({
        id: n.id,
        label: n.data.label,
        type: n.data.nodeType,
      })),
    [nodes],
  );

  const selectedRunView = selectedId ? runner.nodeRuns[selectedId] : undefined;

  const onPublish = async () => {
    const ok = await confirm({
      title: '发布当前草稿？',
      description:
        '冻结当前 draft 为新版本（published_version + 1）；老版本仅 freeze 在 published_spec，不可恢复。',
    });
    if (ok) publishMut.mutate();
  };

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
          {graph.published_version && graph.published_version > 0 ? (
            <span
              className="ml-2 inline-flex items-center gap-1 rounded bg-emerald-50 px-1.5 py-0.5 text-[10.5px] text-emerald-700"
              title={
                graph.published_at
                  ? `最近发布: ${new Date(graph.published_at).toLocaleString()}`
                  : ''
              }
            >
              <Rocket className="h-3 w-3" /> 已发布 v{graph.published_version}
            </span>
          ) : (
            <span className="ml-2 inline-flex items-center gap-1 rounded bg-amber-50 px-1.5 py-0.5 text-[10.5px] text-amber-700">
              草稿
            </span>
          )}
          {dirty && (
            <span
              className="inline-flex items-center gap-1 text-[10.5px] text-amber-600"
              title="有未保存改动"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
              未保存
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {runner.phase === 'success' && (
            <span className="text-[11px] text-emerald-600">
              ✓ {runner.durationMs ?? 0}ms
            </span>
          )}
          {runner.phase === 'failed' && (
            <span className="text-[11px] text-rose-600">✗ 执行失败</span>
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
            onClick={() => setRunOpen(true)}
            title="给输入、跑一次、看每节点输出"
          >
            <Play className="mr-1 h-3 w-3" />
            运行
          </Button>
          <Button
            size="sm"
            onClick={() => saveMut.mutate()}
            disabled={saveMut.isPending}
          >
            <Save className="mr-1 h-3 w-3" />
            保存
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onPublish}
            disabled={publishMut.isPending}
            title="freeze 当前 draft 为新 published 版本"
          >
            <Rocket className="mr-1 h-3 w-3" />
            发布
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
            onNodesChange={handleNodesChange}
            onEdgesChange={handleEdgesChange}
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
            runView={selectedRunView}
            onChange={updateSelectedSpec}
            onDelete={deleteSelected}
          />
        )}
      </div>

      {runOpen && (
        <RunDialog
          open={runOpen}
          onOpenChange={setRunOpen}
          graphId={String(graph.id)}
          graphName={graph.name}
          isDirty={dirty}
          runner={runner}
          nodeMeta={nodeMeta}
        />
      )}
    </div>
  );
};

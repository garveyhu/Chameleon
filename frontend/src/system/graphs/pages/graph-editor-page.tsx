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
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Background,
  BackgroundVariant,
  MiniMap,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from '@xyflow/react';
import type { Connection, Edge, EdgeChange, NodeChange, Node as RFNode } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  Bot,
  ChevronDown,
  Copy,
  History,
  MessageSquare,
  Play,
  Rocket,
  Save,
  Trash2,
} from 'lucide-react';

import { RequireAuth } from '@/core/components/common/permission-guard';
import { Spinner } from '@/core/components/common/spinner';
import { Button } from '@/core/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/core/components/ui/dropdown-menu';
import { cn } from '@/core/lib/cn';
import { confirm } from '@/core/lib/confirm';
import { toast } from '@/core/lib/toast';
import { useWorkflowStore } from '@/core/stores/workflow';
import type { EntityId } from '@/core/types/api';
import { GraphAppRail } from '@/system/graphs/components/app-shell/graph-app-rail';
import type { EditorTab } from '@/system/graphs/components/app-shell/graph-app-rail';
import { ChatDebugDialog } from '@/system/graphs/components/chat-debug-dialog';
import { NodeInspector } from '@/system/graphs/components/node-inspector';
import { NodePalette } from '@/system/graphs/components/node-palette';
import { ZoomControl } from '@/system/graphs/components/zoom-control';
import { GraphNode } from '@/system/graphs/components/nodes/graph-node';
import type { GraphNodeData } from '@/system/graphs/components/nodes/graph-node';
import { AgentApiDocView } from '@/api-docs/components/agent-api-doc-view';
import { RunDialog } from '@/system/graphs/components/run-dialog';
import { ObserveView } from '@/system/graphs/components/views/observe-view';
import { useGraphHistory } from '@/system/graphs/hooks/use-graph-history';
import { useGraphRunner } from '@/system/graphs/hooks/use-graph-runner';
import { TYPE_META } from '@/system/graphs/lib/node-meta';
import { defaultLabel, rfToSpec, specToRf } from '@/system/graphs/lib/rf-spec';
import { graphApi } from '@/system/graphs/services/graph';
import type { GraphDetail, GraphKind, GraphNodeType, NodeSpec } from '@/system/graphs/types/graph';

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
      onReturn={() => nav('/agents')}
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
  const qc = useQueryClient();
  const [nodes, setNodes, onNodesChange] = useNodesState<RFNode<GraphNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const selectedId = useWorkflowStore(s => s.selectedNodeId);
  const setSelectedId = useWorkflowStore(s => s.selectNode);
  const resetWorkflow = useWorkflowStore(s => s.reset);
  const idSeqRef = useRef(0);
  const rfWrapperRef = useRef<HTMLDivElement>(null);
  const rfInstance = useReactFlow();

  const [dirty, setDirty] = useState(false);
  // 日志页受控展开的 run（点击日志列表行展开详情）
  const [logRunId, setLogRunId] = useState<EntityId | null>(null);
  const [runOpen, setRunOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  // 本地持有 kind（EditorBody 按 graph.id keyed，初值取一次）；切换时直存不刷详情，避免清空未存画布
  const [kind, setKind] = useState<GraphKind>(graph.kind);
  const isChat = kind === 'chatflow';
  const [tab, setTab] = useState<EditorTab>('orchestrate');

  // 撤销/重做历史（画布结构操作）；inspector 配置编辑按节点+时间窗口合并入历史
  const markDirty = useCallback(() => setDirty(true), []);
  const {
    commit: histCommit,
    undo: histUndo,
    redo: histRedo,
  } = useGraphHistory({
    nodes,
    edges,
    setNodes,
    setEdges,
    onApplied: markDirty,
  });
  const lastEditAtRef = useRef(0);
  const lastEditNodeRef = useRef<string | null>(null);

  // 点击 palette → 节点跟随光标、点画布落位（Dify click-to-place）
  const [pendingType, setPendingType] = useState<GraphNodeType | null>(null);
  const ghostRef = useRef<HTMLDivElement>(null);

  // 节点右键菜单（复制 / 删除）
  const [ctxMenu, setCtxMenu] = useState<{
    x: number;
    y: number;
    nodeId: string;
    nodeType: GraphNodeType;
  } | null>(null);

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

  // Cmd/Ctrl+Z 撤销、Cmd/Ctrl+Shift+Z（或 Ctrl+Y）重做；仅编排页，输入框内不拦截（交原生文本撤销）
  useEffect(() => {
    if (tab !== 'orchestrate') return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setPendingType(null);
        setCtxMenu(null);
        return;
      }
      if (!(e.metaKey || e.ctrlKey)) return;
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)
      ) {
        return;
      }
      const k = e.key.toLowerCase();
      if (k === 'z') {
        e.preventDefault();
        if (e.shiftKey) histRedo();
        else histUndo();
      } else if (k === 'y') {
        e.preventDefault();
        histRedo();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [tab, histUndo, histRedo]);

  const saveMut = useMutation({
    mutationFn: () => {
      const spec = rfToSpec(nodes, edges);
      return graphApi.update(graph.id, { spec });
    },
    onSuccess: () => {
      setDirty(false);
      onSaved();
      toast.success('已保存');
    },
    onError: e => toast.error(`保存失败：${(e as Error).message}`),
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
      // 删除走历史（拖拽移动在 onNodeDragStart 记，新增在 addNode 记）
      if (changes.some(c => c.type === 'remove')) histCommit();
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
    [onNodesChange, histCommit],
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange<Edge>[]) => {
      if (changes.some(c => c.type === 'remove')) histCommit();
      onEdgesChange(changes);
      if (changes.some(c => c.type === 'remove' || c.type === 'add')) {
        setDirty(true);
      }
    },
    [onEdgesChange, histCommit],
  );

  const onConnect = useCallback(
    (conn: Connection) => {
      histCommit();
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
    [setEdges, histCommit],
  );

  const nextNodeId = () => {
    idSeqRef.current += 1;
    return `n${idSeqRef.current}`;
  };

  const addNode = useCallback(
    (type: GraphNodeType, position?: { x: number; y: number }) => {
      histCommit();
      const newId = nextNodeId();
      const pos = position ?? rfInstance.screenToFlowPosition({ x: 300, y: 200 });
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
    [rfInstance, setNodes, setSelectedId, histCommit],
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
      // 配置编辑合并入历史：同一节点 700ms 内的连续编辑只记一次改前快照
      const now = Date.now();
      if (now - lastEditAtRef.current > 700 || lastEditNodeRef.current !== next.id) {
        histCommit();
      }
      lastEditAtRef.current = now;
      lastEditNodeRef.current = next.id;
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
    [setNodes, histCommit],
  );

  const deleteNode = useCallback(
    (id: string) => {
      const node = nodes.find(n => n.id === id);
      if (!node || node.data.nodeType === 'start') return; // start 不可删
      histCommit();
      setNodes(ns => ns.filter(n => n.id !== id));
      setEdges(es => es.filter(e => e.source !== id && e.target !== id));
      setSelectedId(null);
      setDirty(true);
    },
    [nodes, setEdges, setNodes, setSelectedId, histCommit],
  );

  const deleteSelected = useCallback(() => {
    if (selectedId) deleteNode(selectedId);
  }, [selectedId, deleteNode]);

  const duplicateNode = useCallback(
    (id: string) => {
      const src = nodes.find(n => n.id === id);
      if (!src || src.data.nodeType === 'start') return; // start 唯一，不复制
      histCommit();
      const newId = nextNodeId();
      const srcData = (src.data as { _spec?: { data?: Record<string, unknown> } })._spec?.data;
      const clone: RFNode<GraphNodeData> = {
        ...src,
        id: newId,
        position: { x: src.position.x + 48, y: src.position.y + 48 },
        selected: false,
        data: {
          ...src.data,
          label: `${src.data.label} 副本`,
          _spec: { data: { ...(srcData ?? {}) } },
        } as GraphNodeData,
      };
      setNodes(ns => ns.concat(clone));
      setSelectedId(newId);
      setDirty(true);
    },
    [nodes, setNodes, setSelectedId, histCommit],
  );

  const kindMut = useMutation({
    mutationFn: (next: GraphKind) => graphApi.update(graph.id, { kind: next }),
    onSuccess: (_d, next) => {
      setKind(next);
      qc.invalidateQueries({ queryKey: ['graphs'] });
      toast.success(next === 'chatflow' ? '已切到对话型' : '已切到流程型');
    },
    onError: e => toast.error(`切换类型失败：${(e as Error).message}`),
  });

  // 切换 kind 守卫：流程型不使用 Answer 节点，图里若有则切换前确认
  const handleKindChange = useCallback(
    async (next: GraphKind) => {
      if (next === kind) return;
      if (next === 'workflow') {
        const answerCount = nodes.filter(n => n.data.nodeType === 'answer').length;
        if (answerCount > 0) {
          const ok = await confirm({
            title: '切换为流程型？',
            description: `流程型的最终输出走 End 节点，不使用 Answer 节点。当前画布有 ${answerCount} 个 Answer 节点，切换后无法再新增同类节点，已有的也不会在运行时生效。建议先用 End 节点承接输出。仍要切换？`,
            confirmText: '仍要切换',
            danger: true,
          });
          if (!ok) return;
        }
      }
      kindMut.mutate(next);
    },
    [kind, nodes, kindMut],
  );

  const publishMut = useMutation({
    mutationFn: () => graphApi.publish(graph.id),
    onSuccess: detail => {
      toast.success(`已发布 v${detail.published_version}`);
      onSaved();
    },
    onError: e => toast.error(`发布失败：${(e as Error).message}`),
  });

  const publishAgentMut = useMutation({
    mutationFn: async () => {
      if (dirty) await saveMut.mutateAsync();
      return graphApi.publishAsAgent(graph.id);
    },
    onSuccess: r => {
      toast.success(`已发布为智能体：${r.agent_key}（可在「智能体」页调用）`);
      onSaved();
    },
    onError: e => toast.error(`发布为智能体失败：${(e as Error).message}`),
  });

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

  // A2：start 节点配置的开场白 / 建议问题（喂给对话调试面板）
  const startChatCfg = useMemo(() => {
    const start = nodes.find(n => n.data.nodeType === 'start');
    const d =
      (start?.data as { _spec?: { data?: Record<string, unknown> } } | undefined)?._spec?.data ??
      {};
    return {
      opener: d.opener as string | undefined,
      suggested: d.suggested_questions as string[] | undefined,
    };
  }, [nodes]);

  const onPublish = async () => {
    const ok = await confirm({
      title: '发布当前草稿？',
      description:
        '冻结当前 draft 为新版本（published_version + 1）；老版本仅 freeze 在 published_spec，不可恢复。',
    });
    if (ok) publishMut.mutate();
  };

  const onPublishAgent = async () => {
    const ok = await confirm({
      title: '发布为智能体？',
      description: `将冻结当前草稿并暴露成一个可对话智能体（agent_key=${graph.graph_key}），可在「智能体」页和统一 agent 端点调用。`,
    });
    if (ok) publishAgentMut.mutate();
  };

  // ── render ───────────────────────────────────────────────

  return (
    <RequireAuth>
      <div className="flex h-screen bg-[var(--color-warm)]">
        <GraphAppRail
          graph={graph}
          kind={kind}
          onKindChange={handleKindChange}
          tab={tab}
          onTab={setTab}
          onReturn={onReturn}
          dirty={dirty}
          saving={saveMut.isPending}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          {tab === 'orchestrate' && (
            <div className="relative min-h-0 flex-1">
              <div
                ref={rfWrapperRef}
                className={cn('absolute inset-0', pendingType && 'cursor-copy')}
                onDrop={onDrop}
                onDragOver={onDragOver}
                onMouseMove={e => {
                  if (pendingType && ghostRef.current) {
                    ghostRef.current.style.transform = `translate(${e.clientX + 10}px, ${e.clientY + 10}px)`;
                  }
                }}
              >
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  onNodesChange={handleNodesChange}
                  onEdgesChange={handleEdgesChange}
                  onConnect={onConnect}
                  onNodeDragStart={() => histCommit()}
                  onNodeClick={(_e, n) => {
                    setSelectedId(n.id);
                    setCtxMenu(null);
                  }}
                  onNodeContextMenu={(e, n) => {
                    e.preventDefault();
                    setCtxMenu({
                      x: e.clientX,
                      y: e.clientY,
                      nodeId: n.id,
                      nodeType: n.data.nodeType,
                    });
                  }}
                  onPaneClick={e => {
                    setCtxMenu(null);
                    if (pendingType) {
                      const pos = rfInstance.screenToFlowPosition({
                        x: e.clientX,
                        y: e.clientY,
                      });
                      addNode(pendingType, pos);
                      setPendingType(null);
                    } else {
                      setSelectedId(null);
                    }
                  }}
                  nodeTypes={NODE_TYPES}
                  fitView
                  proOptions={{ hideAttribution: true }}
                  defaultEdgeOptions={{ type: 'smoothstep' }}
                >
                  <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
                  <MiniMap
                    pannable
                    zoomable
                    className="!bg-warm-2"
                    position="bottom-right"
                    style={{
                      right: selectedSpec ? 340 : 12,
                      bottom: 50, // 留位置给下方自定义缩放栏
                      margin: 0, // 覆盖默认 15px 边距，与 ZoomControl 右对齐
                    }}
                  />
                  <Panel
                    position="bottom-right"
                    style={{ right: selectedSpec ? 340 : 12, bottom: 12, margin: 0 }}
                  >
                    <ZoomControl />
                  </Panel>
                </ReactFlow>

                {/* 左上角运行事件状态（Dify 套路） */}
                {runner.phase !== 'idle' && (
                  <div className="absolute top-3 left-3 z-20 flex items-center gap-1.5 rounded-lg border border-stone-200/70 bg-white/90 px-2.5 py-1 text-[11.5px] shadow-md backdrop-blur">
                    {runner.phase === 'running' && (
                      <>
                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500" />
                        <span className="text-blue-600">运行中…</span>
                      </>
                    )}
                    {runner.phase === 'success' && (
                      <span className="text-emerald-600">
                        ✓ 运行成功 · {runner.durationMs ?? 0}ms
                      </span>
                    )}
                    {runner.phase === 'failed' && <span className="text-rose-600">✗ 运行失败</span>}
                  </div>
                )}

                {/* 跟随光标的节点幽灵（点击 palette 后，点画布落位） */}
                {pendingType && (
                  <div ref={ghostRef} className="pointer-events-none fixed top-0 left-0 z-50">
                    <div
                      className={cn(
                        'flex items-center gap-1.5 rounded-md border-2 border-dashed bg-white/95 px-2.5 py-1.5 text-[11.5px] font-medium shadow-lg',
                        (TYPE_META[pendingType] ?? TYPE_META.noop).color,
                      )}
                    >
                      {(() => {
                        const Icon = (TYPE_META[pendingType] ?? TYPE_META.noop).icon;
                        return <Icon className="h-3.5 w-3.5" />;
                      })()}
                      {(TYPE_META[pendingType] ?? TYPE_META.noop).label}
                      <span className="text-[10px] font-normal text-stone-400">
                        点击画布放置 · Esc 取消
                      </span>
                    </div>
                  </div>
                )}

                {/* 浮层工具条 —— 钉右上角；撤销/重做走 ⌘Z 快捷键不占位 */}
                <div className="absolute top-3 right-3 z-20 flex items-center gap-1.5 rounded-xl border border-stone-200/70 bg-white/85 px-2 py-1.5 shadow-md backdrop-blur">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setTab('monitor')}
                    title="查看运行日志"
                  >
                    <History className="h-3 w-3" />
                  </Button>

                  {/* 测试：对话型→对话调试，流程型→运行（一个就够） */}
                  {isChat ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setChatOpen(true)}
                      title="多轮对话试聊当前草稿（不必先发布）"
                    >
                      <MessageSquare className="mr-1 h-3 w-3" />
                      对话调试
                    </Button>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setRunOpen(true)}
                      title="给输入、跑一次、看每节点输出"
                    >
                      <Play className="mr-1 h-3 w-3" />
                      运行
                    </Button>
                  )}

                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => saveMut.mutate()}
                    disabled={saveMut.isPending}
                  >
                    <Save className="mr-1 h-3 w-3" />
                    保存
                  </Button>

                  {/* 发布：合并成一个下拉（发布版本 / 发布为智能体） */}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        size="sm"
                        disabled={publishMut.isPending || publishAgentMut.isPending}
                      >
                        <Rocket className="mr-1 h-3 w-3" />
                        发布
                        <ChevronDown className="ml-0.5 h-3 w-3 opacity-70" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-44">
                      <DropdownMenuItem onSelect={onPublish} className="text-[12px]">
                        <Rocket className="mr-2 h-3.5 w-3.5 text-stone-500" />
                        发布版本
                      </DropdownMenuItem>
                      {isChat && (
                        <DropdownMenuItem onSelect={onPublishAgent} className="text-[12px]">
                          <Bot className="mr-2 h-3.5 w-3.5 text-stone-500" />
                          发布为智能体
                        </DropdownMenuItem>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>

                {/* 浮层编辑栏 —— 选中节点时悬浮于画布右侧（Dify 套路） */}
                {selectedSpec && (
                  <div className="bg-warm-2/95 absolute top-16 right-3 bottom-3 z-10 w-80 overflow-hidden rounded-xl border border-stone-200/70 shadow-xl backdrop-blur">
                    <NodeInspector
                      node={selectedSpec}
                      runView={selectedRunView}
                      peerNodes={nodes
                        .filter(n => n.id !== selectedId)
                        .map(n => ({
                          id: n.id,
                          label: n.data.label,
                          type: n.data.nodeType,
                        }))}
                      onChange={updateSelectedSpec}
                      onDelete={deleteSelected}
                    />
                  </div>
                )}

                {/* 浮动节点面板（Dify 风：「+」按钮悬浮卡片，点开滑出节点） */}
                <NodePalette kind={kind} onAdd={t => setPendingType(t)} />
              </div>
            </div>
          )}

          {tab === 'api' && <AgentApiDocView graph={graph} />}
          {tab === 'monitor' && (
            <ObserveView
              graphId={graph.id}
              graphName={graph.name}
              openRunId={logRunId}
              onOpenRun={setLogRunId}
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

        {chatOpen && (
          <ChatDebugDialog
            open={chatOpen}
            onOpenChange={setChatOpen}
            graphId={String(graph.id)}
            graphName={graph.name}
            isDirty={dirty}
            save={save}
            opener={startChatCfg.opener}
            suggestedQuestions={startChatCfg.suggested}
          />
        )}

        {/* 节点右键菜单 */}
        {ctxMenu && (
          <>
            <div
              className="fixed inset-0 z-40"
              onClick={() => setCtxMenu(null)}
              onContextMenu={e => {
                e.preventDefault();
                setCtxMenu(null);
              }}
            />
            <div
              className="shadow-pop fixed z-50 min-w-[150px] overflow-hidden rounded-lg border border-stone-200 bg-white py-1"
              style={{ left: ctxMenu.x, top: ctxMenu.y }}
            >
              {ctxMenu.nodeType === 'start' ? (
                <div className="px-3 py-1.5 text-[12px] text-stone-400">
                  起始节点不可复制 / 删除
                </div>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => {
                      duplicateNode(ctxMenu.nodeId);
                      setCtxMenu(null);
                    }}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12.5px] text-stone-700 transition hover:bg-stone-100"
                  >
                    <Copy className="h-3.5 w-3.5 text-stone-400" />
                    复制节点
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      deleteNode(ctxMenu.nodeId);
                      setCtxMenu(null);
                    }}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12.5px] text-rose-600 transition hover:bg-rose-50"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    删除节点
                  </button>
                </>
              )}
            </div>
          </>
        )}
      </div>
    </RequireAuth>
  );
};

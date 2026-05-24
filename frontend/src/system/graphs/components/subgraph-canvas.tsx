/** SubgraphCanvas —— 自包含的子图可视化编辑器（iteration.body / parallel.branches[].body）
 *
 * 复用主编辑器的 palette / inspector / 节点渲染 / spec 双向映射，但去掉运行 / 保存 /
 * 全局选中 store（用本地 selectedId，避免与主画布选中打架）。
 * 每次画布变化把最新 spec 通过 onChange 推给父（modal 持 draft，应用时落回）。
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
import type { Connection, Edge, Node as RFNode } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { NodeInspector } from '@/system/graphs/components/node-inspector';
import { NodePalette } from '@/system/graphs/components/node-palette';
import { GraphNode } from '@/system/graphs/components/nodes/graph-node';
import type { GraphNodeData } from '@/system/graphs/components/nodes/graph-node';
import { defaultLabel, rfToSpec, specToRf } from '@/system/graphs/lib/rf-spec';
import type {
  GraphNodeType,
  GraphSpec,
  NodeSpec,
} from '@/system/graphs/types/graph';

const NODE_TYPES = { graphNode: GraphNode } as const;

interface Props {
  spec: GraphSpec;
  onChange: (spec: GraphSpec) => void;
}

export const SubgraphCanvas = ({ spec, onChange }: Props) => (
  <ReactFlowProvider>
    <Inner spec={spec} onChange={onChange} />
  </ReactFlowProvider>
);

const Inner = ({ spec, onChange }: Props) => {
  // 仅初始化一次（modal 按编辑目标 keyed 重挂，故无需随 spec prop 同步）
  const seed = useMemo(() => specToRf(spec), [spec]);
  const [nodes, setNodes, onNodesChange] = useNodesState<RFNode<GraphNodeData>>(
    seed.rfNodes,
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(seed.rfEdges);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const rfInstance = useReactFlow();
  const wrapRef = useRef<HTMLDivElement>(null);
  const idSeqRef = useRef(
    Math.max(
      0,
      ...spec.nodes
        .map(n => n.id)
        .filter(id => /^n\d+$/.test(id))
        .map(id => Number(id.slice(1))),
    ),
  );

  // 画布变化 → 推 spec 给父（onChange 应为稳定引用，如 setState）
  useEffect(() => {
    onChange(rfToSpec(nodes, edges));
  }, [nodes, edges, onChange]);

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

  const addNode = useCallback(
    (type: GraphNodeType, position?: { x: number; y: number }) => {
      idSeqRef.current += 1;
      const newId = `n${idSeqRef.current}`;
      const pos =
        position ?? rfInstance.screenToFlowPosition({ x: 280, y: 160 });
      const rfNode: RFNode<GraphNodeData> = {
        id: newId,
        position: pos,
        type: 'graphNode',
        data: {
          label: defaultLabel(type, newId),
          nodeType: type,
          _spec: { data: {} },
        } as GraphNodeData,
      };
      setNodes(ns => ns.concat(rfNode));
      setSelectedId(newId);
    },
    [rfInstance, setNodes],
  );

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      const type = e.dataTransfer.getData(
        'application/x-graph-node-type',
      ) as GraphNodeType;
      if (!type) return;
      const bounds = wrapRef.current?.getBoundingClientRect();
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
    const stored =
      (selectedRfNode.data as { _spec?: { data?: Record<string, unknown> } })
        ._spec ?? {};
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
        ns.map(n =>
          n.id === next.id
            ? ({
                ...n,
                data: {
                  ...n.data,
                  label: next.name || next.id,
                  _spec: { data: next.data || {} },
                } as GraphNodeData,
              } as RFNode<GraphNodeData>)
            : n,
        ),
      );
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
  }, [selectedId, setEdges, setNodes]);

  return (
    <div className="flex h-full min-h-0">
      <NodePalette onAdd={addNode} />
      <div
        ref={wrapRef}
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
      <NodeInspector
        node={selectedSpec}
        onChange={updateSelectedSpec}
        onDelete={deleteSelected}
      />
    </div>
  );
};

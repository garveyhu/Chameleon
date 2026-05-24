/** GraphSpec ↔ React Flow 扁平结构的双向映射 + 默认标签
 *
 * 主编辑器与子图编辑器共用：
 *   后端 spec.nodes[].position {x,y}  ↔  React Flow node.position
 *   后端 spec.edges[].source_handle ↔  React Flow edge.sourceHandle
 *   后端 spec.nodes[].data        ↔  React Flow node.data._spec.data
 */

import type { Edge, Node as RFNode } from '@xyflow/react';

import type { GraphNodeData } from '@/system/graphs/components/nodes/graph-node';
import type {
  EdgeSpec,
  GraphNodeType,
  GraphSpec,
} from '@/system/graphs/types/graph';

interface SpecHolder {
  _spec?: { data?: Record<string, unknown> };
}

export function specToRf(spec: GraphSpec): {
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
      _spec: { data: n.data || {} },
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

export function rfToSpec(
  nodes: RFNode<GraphNodeData>[],
  edges: Edge[],
): GraphSpec {
  return {
    nodes: nodes.map(n => {
      const stored = (n.data as SpecHolder)._spec ?? {};
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

export function defaultLabel(type: GraphNodeType, id: string): string {
  const t: Partial<Record<GraphNodeType, string>> = {
    llm: 'LLM 调用',
    kb: 'KB 检索',
    tool: '工具',
    if_else: '条件分支',
    agent_debate: 'Agent 辩论',
    iteration: '迭代',
    parallel: '并行',
    human_input: '人工输入',
    end: '终态',
    start: '开始',
    noop: '占位',
  };
  return `${t[type] ?? type} · ${id}`;
}

/** 子图初始 spec：一对 start/end + 直连边（与列表页 DEFAULT_SPEC 一致风格） */
export function emptySubgraphSpec(): GraphSpec {
  return {
    nodes: [
      { id: 'start', type: 'start', name: 'Start', position: { x: 80, y: 160 } },
      { id: 'end', type: 'end', name: 'End', position: { x: 460, y: 160 } },
    ],
    edges: [{ id: 'e_start_end', source: 'start', target: 'end' }],
  };
}

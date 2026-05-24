/** Gantt 纯计算：树拍平（含折叠）+ 时间轴几何，无 React 依赖 */

import type { TraceTreeNode } from '@/system/call_logs/types/call-log';

export interface GanttRow {
  node: TraceTreeNode;
  depth: number;
  hasChildren: boolean;
  collapsed: boolean;
}

/** DFS 拍平为线性行；折叠节点的子树不展开 */
export function flattenTrace(
  root: TraceTreeNode,
  collapsedMap: Record<string, boolean>,
): GanttRow[] {
  const rows: GanttRow[] = [];
  const walk = (node: TraceTreeNode, depth: number) => {
    const hasChildren = node.children.length > 0;
    const collapsed = !!collapsedMap[node.request_id];
    rows.push({ node, depth, hasChildren, collapsed });
    if (hasChildren && !collapsed) {
      for (const ch of node.children) walk(ch, depth + 1);
    }
  };
  walk(root, 0);
  return rows;
}

export interface TimeBounds {
  /** 整棵树最早的开始时间（epoch ms） */
  minMs: number;
  /** 整体跨度 ms（≥ 1 防除零） */
  totalMs: number;
}

/** 遍历全树（忽略折叠）求稳定的时间轴范围 */
export function computeBounds(root: TraceTreeNode): TimeBounds {
  let minMs = Infinity;
  let maxMs = -Infinity;
  const walk = (n: TraceTreeNode) => {
    const start = Date.parse(n.created_at);
    if (!Number.isNaN(start)) {
      minMs = Math.min(minMs, start);
      maxMs = Math.max(maxMs, start + Math.max(0, n.duration_ms ?? 0));
    }
    n.children.forEach(walk);
  };
  walk(root);
  if (!Number.isFinite(minMs)) return { minMs: 0, totalMs: 1 };
  return { minMs, totalMs: Math.max(1, maxMs - minMs) };
}

export interface BarGeometry {
  /** 左偏移占比 0–100 */
  leftPct: number;
  /** 宽度占比 0–100（至少 0.6 保证可见） */
  widthPct: number;
  /** 相对 trace 起点的开始偏移 ms */
  offsetMs: number;
}

export function barGeometry(
  node: TraceTreeNode,
  bounds: TimeBounds,
): BarGeometry {
  const start = Date.parse(node.created_at);
  const offsetMs = Number.isNaN(start) ? 0 : start - bounds.minMs;
  const dur = Math.max(0, node.duration_ms ?? 0);
  const leftPct = Math.min(100, Math.max(0, (offsetMs / bounds.totalMs) * 100));
  const rawWidth = (dur / bounds.totalMs) * 100;
  const widthPct = Math.min(100 - leftPct, Math.max(0.6, rawWidth));
  return { leftPct, widthPct, offsetMs };
}

/** 生成时间刻度（ruler）：在 0..totalMs 间均匀取 ticks 个点 */
export function timeTicks(totalMs: number, count = 5): number[] {
  const ticks: number[] = [];
  for (let i = 0; i <= count; i++) ticks.push((totalMs / count) * i);
  return ticks;
}

/** 工作流变量检查 —— 扫描节点配置里的 {{#...#}} 引用，标出指向不存在节点的坏引用
 *
 * 合法根：sys（系统变量）/ conversation（会话变量）/ 任一存在的节点 id。
 * 其余视为坏引用（多半是节点删除 / 改名后留下的悬空引用）。
 */
import type { Node as RFNode } from '@xyflow/react';

import type { GraphNodeData } from '@/system/graphs/components/nodes/graph-node';

export interface VarIssue {
  nodeId: string;
  nodeLabel: string;
  token: string;
  reason: string;
}

const TOKEN_RE = /\{\{#\s*([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)\s*#\}\}/g;

function collectStrings(val: unknown, out: string[]): void {
  if (typeof val === 'string') {
    out.push(val);
  } else if (Array.isArray(val)) {
    for (const v of val) collectStrings(v, out);
  } else if (val && typeof val === 'object') {
    for (const v of Object.values(val)) collectStrings(v, out);
  }
}

export function lintGraph(nodes: RFNode<GraphNodeData>[]): VarIssue[] {
  const ids = new Set(nodes.map(n => n.id));
  const issues: VarIssue[] = [];
  const seen = new Set<string>();

  for (const n of nodes) {
    const data = (n.data as { _spec?: { data?: Record<string, unknown> } })._spec?.data ?? {};
    const strings: string[] = [];
    collectStrings(data, strings);

    for (const s of strings) {
      TOKEN_RE.lastIndex = 0;
      let m: RegExpExecArray | null;
      while ((m = TOKEN_RE.exec(s)) !== null) {
        const root = m[1].split('.')[0];
        if (root === 'sys' || root === 'conversation') continue;
        if (ids.has(root)) continue;
        const key = `${n.id}::${m[0]}`;
        if (seen.has(key)) continue;
        seen.add(key);
        issues.push({
          nodeId: n.id,
          nodeLabel: n.data.label,
          token: m[0],
          reason: `引用了不存在的节点「${root}」`,
        });
      }
    }
  }
  return issues;
}

/** 编排方式徽标 —— 由 agent 的 source + 关联 graph 的 kind 推导展示
 *
 * 纯展示组件：接 props 出 UI，色阶用 Tailwind 调色板类（与全站徽标体系一致）。
 * 推导逻辑见 @/core/lib/orchestration。
 */

import { type OrchestrationKind, resolveOrchestrationKind } from '@/core/lib/orchestration';

const KIND_DEFS: Record<OrchestrationKind, { label: string; cls: string }> = {
  code: { label: '代码', cls: 'bg-indigo-50 text-indigo-700' },
  chatflow: { label: '对话编排', cls: 'bg-sky-50 text-sky-700' },
  workflow: { label: '流程编排', cls: 'bg-violet-50 text-violet-700' },
  external: { label: '外部', cls: 'bg-amber-50 text-amber-700' },
};

export const OrchestrationBadge = ({
  source,
  graphKind,
}: {
  source?: string | null;
  graphKind?: string | null;
}) => {
  const kind = resolveOrchestrationKind(source, graphKind);
  if (!kind) {
    return <span className="text-[10.5px] text-stone-300">—</span>;
  }
  const def = KIND_DEFS[kind];
  return (
    <span
      className={`inline-flex shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${def.cls}`}
    >
      {def.label}
    </span>
  );
};

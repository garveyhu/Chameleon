/** iteration.body / parallel.branches 的可视化编辑入口（替代裸 JSON）
 *
 * SubgraphField：单个子图 —— 摘要 + 「可视化编辑」打开 SubgraphEditorModal。
 * ParallelBranchesField：分支列表 —— 增删改 key + 各自子图编辑。
 */

import { Network, Pencil, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { SubgraphEditorModal } from '@/system/graphs/components/subgraph-editor-modal';
import { emptySubgraphSpec } from '@/system/graphs/lib/rf-spec';
import type { GraphSpec } from '@/system/graphs/types/graph';

interface ParallelBranch {
  key: string;
  body: GraphSpec;
}

function asSpec(v: unknown): GraphSpec {
  if (
    v &&
    typeof v === 'object' &&
    Array.isArray((v as GraphSpec).nodes) &&
    Array.isArray((v as GraphSpec).edges)
  ) {
    return v as GraphSpec;
  }
  return emptySubgraphSpec();
}

function summary(spec: GraphSpec): string {
  return `${spec.nodes.length} 节点 · ${spec.edges.length} 边`;
}

// ── 单子图（iteration.body）─────────────────────────────────

export const SubgraphField = ({
  label,
  hint,
  title,
  spec: rawSpec,
  onChange,
}: {
  label: string;
  hint?: string;
  title: string;
  spec: unknown;
  onChange: (spec: GraphSpec) => void;
}) => {
  const spec = asSpec(rawSpec);
  const [open, setOpen] = useState(false);

  return (
    <div>
      <label className="mb-1 block text-[11px] text-stone-600">{label}</label>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex w-full items-center gap-2 rounded-md border border-stone-200 bg-white px-2 py-2 text-left text-[11.5px] transition hover:border-stone-300 hover:bg-stone-50"
      >
        <Network className="h-3.5 w-3.5 shrink-0 text-sky-600" />
        <span className="flex-1 text-stone-700">子图</span>
        <span className="font-mono text-[10.5px] text-stone-400">
          {summary(spec)}
        </span>
        <Pencil className="h-3 w-3 text-stone-400" />
      </button>
      {hint && (
        <div className="mt-1 text-[10.5px] leading-snug text-stone-500">
          {hint}
        </div>
      )}
      {open && (
        <SubgraphEditorModal
          open={open}
          onOpenChange={setOpen}
          title={title}
          spec={spec}
          onApply={onChange}
        />
      )}
    </div>
  );
};

// ── 分支列表（parallel.branches）────────────────────────────

function asBranches(v: unknown): ParallelBranch[] {
  if (!Array.isArray(v)) return [];
  return v.map((b, i) => {
    const o = (b ?? {}) as { key?: unknown; body?: unknown };
    return {
      key: typeof o.key === 'string' ? o.key : `b${i + 1}`,
      body: asSpec(o.body),
    };
  });
}

export const ParallelBranchesField = ({
  branches: raw,
  onChange,
}: {
  branches: unknown;
  onChange: (branches: ParallelBranch[]) => void;
}) => {
  const branches = asBranches(raw);
  const [editing, setEditing] = useState<number | null>(null);

  const update = (next: ParallelBranch[]) => onChange(next);

  const addBranch = () => {
    const keys = new Set(branches.map(b => b.key));
    let i = branches.length + 1;
    let key = `b${i}`;
    while (keys.has(key)) key = `b${++i}`;
    update([...branches, { key, body: emptySubgraphSpec() }]);
  };

  const setKey = (idx: number, key: string) =>
    update(branches.map((b, i) => (i === idx ? { ...b, key } : b)));

  const setBody = (idx: number, body: GraphSpec) =>
    update(branches.map((b, i) => (i === idx ? { ...b, body } : b)));

  const removeAt = (idx: number) =>
    update(branches.filter((_, i) => i !== idx));

  return (
    <div>
      <label className="mb-1 block text-[11px] text-stone-600">
        分支（2–20 条，同一 input fork 后并发跑）
      </label>
      <div className="space-y-1.5">
        {branches.length === 0 ? (
          <div className="rounded-md border border-dashed border-stone-200 px-2 py-3 text-center text-[11px] text-stone-400">
            还没有分支；点下方「添加分支」
          </div>
        ) : (
          branches.map((b, idx) => (
            <div
              key={idx}
              className="flex items-center gap-1.5 rounded-md border border-stone-200 bg-white px-1.5 py-1.5"
            >
              <Input
                value={b.key}
                onChange={e => setKey(idx, e.target.value)}
                placeholder="分支 key"
                className="h-7 w-24 font-mono text-[11.5px]"
              />
              <span className="flex-1 truncate font-mono text-[10.5px] text-stone-400">
                {summary(b.body)}
              </span>
              <button
                type="button"
                onClick={() => setEditing(idx)}
                title="编辑子图"
                className="rounded p-1 text-stone-400 hover:bg-stone-100 hover:text-stone-700"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => removeAt(idx)}
                title="删除分支"
                className="rounded p-1 text-stone-400 hover:bg-rose-50 hover:text-rose-600"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))
        )}
      </div>
      <Button
        variant="outline"
        size="sm"
        onClick={addBranch}
        className="mt-1.5 w-full"
      >
        <Plus className="mr-1 h-3 w-3" />
        添加分支
      </Button>

      {editing != null && branches[editing] && (
        <SubgraphEditorModal
          open={editing != null}
          onOpenChange={o => !o && setEditing(null)}
          title={`分支「${branches[editing].key}」子图`}
          spec={branches[editing].body}
          onApply={spec => setBody(editing, spec)}
        />
      )}
    </div>
  );
};

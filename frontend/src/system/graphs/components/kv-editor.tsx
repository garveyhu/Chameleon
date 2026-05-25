/** 键值 / 分类行编辑器 —— 替代节点配置里的裸 JSON textarea
 *
 * KeyValueEditor: dict {key: 模板} ⇄ 行（key 输入 + value 输入，value 可插变量）。
 *   用于 assign.assignments / http.headers / aggregator.fields。
 * CategoriesEditor: [{key, description}] ⇄ 行，用于 classifier.categories。
 *
 * 安全用内部 state：本组件随所在 DataForm 按 node.id keyed 重挂，
 * 一个节点的编辑会话内 state 即真相，每次改动 emit 重建后的结构上去。
 */

import { Plus, X } from 'lucide-react';
import { useRef, useState } from 'react';

import { Input } from '@/core/components/ui/input';
import { cn } from '@/core/lib/cn';
import { VarInsert } from '@/system/graphs/components/var-insert';
import type { NodeVarOption } from '@/system/graphs/components/var-insert';

// ── KeyValueEditor（dict 形）────────────────────────────────

interface KvRow {
  id: number;
  k: string;
  v: string;
}

function dictToRows(value: unknown): KvRow[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
  return Object.entries(value as Record<string, unknown>).map(([k, v], i) => ({
    id: i,
    k,
    v: typeof v === 'string' ? v : JSON.stringify(v),
  }));
}

function rowsToDict(rows: KvRow[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const r of rows) {
    const key = r.k.trim();
    if (key) out[key] = r.v;
  }
  return out;
}

export const KeyValueEditor = ({
  label,
  value,
  onChange,
  keyPlaceholder = 'key',
  valuePlaceholder = 'value',
  nodeVars,
  valueMono,
  hint,
}: {
  label: string;
  value: unknown;
  onChange: (dict: Record<string, string>) => void;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
  /** 传则每行 value 下出现变量插入条 */
  nodeVars?: NodeVarOption[];
  valueMono?: boolean;
  hint?: string;
}) => {
  const [rows, setRows] = useState<KvRow[]>(() => dictToRows(value));
  const seq = useRef(rows.length);

  const emit = (next: KvRow[]) => {
    setRows(next);
    onChange(rowsToDict(next));
  };
  const patchRow = (id: number, patch: Partial<KvRow>) =>
    emit(rows.map(r => (r.id === id ? { ...r, ...patch } : r)));
  const appendValue = (id: number, t: string) =>
    emit(rows.map(r => (r.id === id ? { ...r, v: r.v + t } : r)));
  const add = () => {
    seq.current += 1;
    emit([...rows, { id: seq.current, k: '', v: '' }]);
  };
  const remove = (id: number) => emit(rows.filter(r => r.id !== id));

  return (
    <div>
      <label className="mb-1 block text-[11px] text-stone-600">{label}</label>
      <div className="space-y-1.5">
        {rows.length === 0 && (
          <div className="rounded-md border border-dashed border-stone-200 px-2 py-2 text-center text-[10.5px] text-stone-400">
            还没有条目
          </div>
        )}
        {rows.map(r => (
          <div
            key={r.id}
            className="rounded-md border border-stone-200 bg-white p-1.5"
          >
            <div className="flex items-center gap-1">
              <Input
                value={r.k}
                onChange={e => patchRow(r.id, { k: e.target.value })}
                placeholder={keyPlaceholder}
                className="h-6 w-24 shrink-0 font-mono text-[11px]"
              />
              <span className="shrink-0 text-stone-300">=</span>
              <Input
                value={r.v}
                onChange={e => patchRow(r.id, { v: e.target.value })}
                placeholder={valuePlaceholder}
                className={cn(
                  'h-6 min-w-0 flex-1 text-[11px]',
                  valueMono && 'font-mono',
                )}
              />
              <button
                type="button"
                onClick={() => remove(r.id)}
                title="删除"
                className="shrink-0 rounded p-0.5 text-stone-400 hover:bg-rose-50 hover:text-rose-600"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
            {nodeVars && (
              <VarInsert
                nodeVars={nodeVars}
                onInsert={t => appendValue(r.id, t)}
              />
            )}
          </div>
        ))}
        <button
          type="button"
          onClick={add}
          className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-[11px] text-stone-500 transition hover:text-stone-800"
        >
          <Plus className="h-3 w-3" />
          添加一项
        </button>
      </div>
      {hint && (
        <div className="mt-1 text-[10.5px] leading-snug text-stone-500">
          {hint}
        </div>
      )}
    </div>
  );
};

// ── CategoriesEditor（classifier 的 [{key, description}]）─────

interface CatRow {
  id: number;
  key: string;
  description: string;
}

function valueToCats(value: unknown): CatRow[] {
  if (!Array.isArray(value)) return [];
  return value.map((c, i) => {
    const o = (c ?? {}) as Record<string, unknown>;
    return {
      id: i,
      key: String(o.key ?? ''),
      description: String(o.description ?? ''),
    };
  });
}

export const CategoriesEditor = ({
  value,
  onChange,
}: {
  value: unknown;
  onChange: (cats: { key: string; description?: string }[]) => void;
}) => {
  const [cats, setCats] = useState<CatRow[]>(() => valueToCats(value));
  const seq = useRef(cats.length);

  const emit = (next: CatRow[]) => {
    setCats(next);
    onChange(
      next
        .filter(c => c.key.trim())
        .map(c => ({
          key: c.key.trim(),
          description: c.description.trim() || undefined,
        })),
    );
  };
  const patch = (id: number, p: Partial<CatRow>) =>
    emit(cats.map(c => (c.id === id ? { ...c, ...p } : c)));
  const add = () => {
    seq.current += 1;
    emit([...cats, { id: seq.current, key: '', description: '' }]);
  };
  const remove = (id: number) => emit(cats.filter(c => c.id !== id));

  return (
    <div>
      <label className="mb-1 block text-[11px] text-stone-600">
        分类（≥2；LLM 据描述判定，输出 category）
      </label>
      <div className="space-y-1.5">
        {cats.map(c => (
          <div
            key={c.id}
            className="flex items-center gap-1 rounded-md border border-stone-200 bg-white p-1.5"
          >
            <Input
              value={c.key}
              onChange={e => patch(c.id, { key: e.target.value })}
              placeholder="key"
              className="h-6 w-20 shrink-0 font-mono text-[11px]"
            />
            <Input
              value={c.description}
              onChange={e => patch(c.id, { description: e.target.value })}
              placeholder="描述（这类问题是…）"
              className="h-6 min-w-0 flex-1 text-[11px]"
            />
            <button
              type="button"
              onClick={() => remove(c.id)}
              title="删除"
              className="shrink-0 rounded p-0.5 text-stone-400 hover:bg-rose-50 hover:text-rose-600"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={add}
          className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-[11px] text-stone-500 transition hover:text-stone-800"
        >
          <Plus className="h-3 w-3" />
          添加分类
        </button>
      </div>
      <div className="mt-1 text-[10.5px] leading-snug text-stone-500">
        下游用 if_else 读 {'{{#本节点id.category#}}'} 分流
      </div>
    </div>
  );
};

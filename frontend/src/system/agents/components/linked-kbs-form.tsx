/** Agent 关联 KB 表单 —— 多选组合框（autocomplete by name） */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, Save, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import { agentApi } from '@/system/agents/services/agent';
import type { LinkedKbItem } from '@/system/agents/types/agent';
import { kbApi } from '@/system/kbs/services/kb';

interface Props {
  agentId: number;
}

export const LinkedKbsForm = ({ agentId }: Props) => {
  const qc = useQueryClient();
  const linkedQ = useQuery({
    queryKey: ['agent-linked-kbs', agentId],
    queryFn: () => agentApi.linkedKbs(agentId),
  });
  const allKbsQ = useQuery({
    queryKey: ['agent-linked-kbs-options'],
    queryFn: () => kbApi.list({ page: 1, page_size: 100 }),
  });

  const [selected, setSelected] = useState<LinkedKbItem[]>([]);
  useEffect(() => {
    if (linkedQ.data) setSelected(linkedQ.data);
  }, [linkedQ.data]);

  const linkedIds = useMemo(
    () => new Set(linkedQ.data?.map(k => k.id) ?? []),
    [linkedQ.data],
  );
  const currentIds = useMemo(() => new Set(selected.map(k => k.id)), [selected]);
  const dirty = useMemo(() => {
    if (linkedIds.size !== currentIds.size) return true;
    for (const id of currentIds) if (!linkedIds.has(id)) return true;
    return false;
  }, [linkedIds, currentIds]);

  const saveMut = useMutation({
    mutationFn: () =>
      agentApi.updateLinkedKbs(
        agentId,
        selected.map(k => k.id),
      ),
    onSuccess: () => {
      toast.success('关联已保存');
      qc.invalidateQueries({ queryKey: ['agent-linked-kbs', agentId] });
    },
    onError: () => toast.error('保存失败'),
  });

  const remove = (id: number) =>
    setSelected(selected.filter(k => k.id !== id));

  const add = (kb: LinkedKbItem) => {
    if (currentIds.has(kb.id)) return;
    setSelected([...selected, kb]);
  };

  return (
    <div className="max-w-[640px] space-y-4">
      <div>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-[13.5px] font-medium text-stone-900">
            已关联 KB
          </h3>
          <span className="text-[11px] text-stone-500">
            agent 调用时会跨这些 KB 检索
          </span>
        </div>
        {linkedQ.isLoading ? (
          <div className="py-6 text-center text-sm text-stone-400">加载中…</div>
        ) : selected.length === 0 ? (
          <div className="rounded-md border border-dashed border-stone-300 bg-stone-50/40 py-6 text-center text-[12.5px] text-stone-400">
            尚未关联任何 KB
          </div>
        ) : (
          <ul className="space-y-1.5">
            {selected.map(k => (
              <li
                key={k.id}
                className="flex items-center justify-between rounded-md border border-stone-200/70 bg-white px-3 py-2"
              >
                <div>
                  <Link
                    to={`/kbs/${k.id}`}
                    className="text-[13px] font-medium text-stone-900 hover:underline"
                  >
                    {k.name}
                  </Link>
                  <div className="mt-0.5 text-[11px] text-stone-500">
                    <span className="font-mono">{k.kb_key}</span>
                    <span className="mx-2 text-stone-300">·</span>
                    <span>{k.embedding_model}</span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => remove(k.id)}
                  className="rounded p-1 text-stone-500 hover:bg-rose-50 hover:text-rose-600"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <KbAutocomplete
          options={allKbsQ.data?.items ?? []}
          excludeIds={currentIds}
          onPick={add}
        />
      </div>

      <div className="flex justify-end">
        <Button
          onClick={() => saveMut.mutate()}
          disabled={!dirty || saveMut.isPending}
        >
          <Save className="mr-1.5 h-3.5 w-3.5" />
          {saveMut.isPending ? '保存中…' : '保存关联'}
        </Button>
      </div>
    </div>
  );
};

interface AutocompleteProps {
  options: Array<{
    id: number;
    kb_key: string;
    name: string;
    description: string | null;
    embedding_model: string;
    embedding_dim: number;
  }>;
  excludeIds: Set<number>;
  onPick: (kb: LinkedKbItem) => void;
}

const KbAutocomplete = ({ options, excludeIds, onPick }: AutocompleteProps) => {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const filtered = useMemo(() => {
    const ql = q.trim().toLowerCase();
    return options
      .filter(o => !excludeIds.has(o.id))
      .filter(
        o =>
          !ql ||
          o.name.toLowerCase().includes(ql) ||
          o.kb_key.toLowerCase().includes(ql),
      )
      .slice(0, 20);
  }, [q, options, excludeIds]);

  return (
    <div ref={rootRef} className="relative">
      <div
        className={cn(
          'flex items-center gap-2 rounded-md border border-stone-200 bg-white px-2 py-1',
        )}
      >
        <Input
          value={q}
          onFocus={() => setOpen(true)}
          onChange={e => {
            setQ(e.target.value);
            setOpen(true);
          }}
          placeholder="按名称 / kb_key 搜索 KB 并点击添加…"
          className="h-7 border-0 px-1 text-[12.5px] focus-visible:ring-0"
        />
        <ChevronDown className="h-3.5 w-3.5 text-stone-400" />
      </div>
      {open && (
        <div className="absolute z-10 mt-1 max-h-[280px] w-full overflow-y-auto rounded-md border border-stone-200 bg-white shadow-md">
          {filtered.length === 0 ? (
            <div className="px-3 py-2 text-[12px] text-stone-400">
              无匹配 KB
            </div>
          ) : (
            filtered.map(o => (
              <button
                key={o.id}
                type="button"
                className="flex w-full flex-col items-start gap-0.5 px-3 py-1.5 text-left text-[12.5px] hover:bg-stone-50"
                onClick={() => {
                  onPick({
                    id: o.id,
                    kb_key: o.kb_key,
                    name: o.name,
                    description: o.description,
                    embedding_model: o.embedding_model,
                    embedding_dim: o.embedding_dim,
                  });
                  setQ('');
                }}
              >
                <span className="font-medium text-stone-900">{o.name}</span>
                <span className="font-mono text-[10.5px] text-stone-500">
                  {o.kb_key} · {o.embedding_model}
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
};

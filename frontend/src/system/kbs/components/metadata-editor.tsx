/** Metadata 编辑器 —— key-value list */

import { Plus, X } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';

interface Props {
  value: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  disabled?: boolean;
}

interface Row {
  key: string;
  value: string;
}

export const MetadataEditor = ({ value, onChange, disabled }: Props) => {
  const initial = useMemo<Row[]>(
    () =>
      Object.entries(value || {}).map(([k, v]) => ({
        key: k,
        value: typeof v === 'string' ? v : JSON.stringify(v),
      })),
    [value],
  );
  const [rows, setRows] = useState<Row[]>(initial);

  const commit = (next: Row[]) => {
    setRows(next);
    const out: Record<string, unknown> = {};
    for (const r of next) {
      if (!r.key.trim()) continue;
      // 尽量保留 JSON 原型
      let parsed: unknown = r.value;
      try {
        parsed = JSON.parse(r.value);
      } catch {
        /* keep string */
      }
      out[r.key.trim()] = parsed;
    }
    onChange(out);
  };

  return (
    <div className="space-y-2">
      {rows.map((r, i) => (
        <div key={i} className="flex items-center gap-2">
          <Input
            placeholder="key"
            value={r.key}
            disabled={disabled}
            className="h-8 w-40 font-mono text-[12.5px]"
            onChange={e => {
              const next = [...rows];
              next[i] = { ...next[i], key: e.target.value };
              commit(next);
            }}
          />
          <Input
            placeholder="value（字符串 / JSON）"
            value={r.value}
            disabled={disabled}
            className="h-8 flex-1 font-mono text-[12.5px]"
            onChange={e => {
              const next = [...rows];
              next[i] = { ...next[i], value: e.target.value };
              commit(next);
            }}
          />
          {!disabled && (
            <button
              type="button"
              className="rounded p-1 text-stone-500 hover:bg-rose-50 hover:text-rose-600"
              onClick={() => commit(rows.filter((_, idx) => idx !== i))}
              aria-label="remove"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      ))}
      {!disabled && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => commit([...rows, { key: '', value: '' }])}
        >
          <Plus className="mr-1 h-3 w-3" /> 添加键值
        </Button>
      )}
    </div>
  );
};

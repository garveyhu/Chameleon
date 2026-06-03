/** JSON / 文本单元格：短文本直显，长文本/对象折叠为单行摘要，点击展开完整带缩进。
 *  脱敏字段（{hash,length,preview}）优先展示 preview。 */
import { useState } from 'react';

import { cn } from '@/core/lib/cn';

interface Props {
  value: unknown;
  className?: string;
}

export const JsonCell = ({ value, className }: Props) => {
  const [open, setOpen] = useState(false);
  if (value == null) return <span className="text-stone-400">—</span>;

  if (typeof value === 'string') {
    if (value.length <= 80) {
      return <span className={cn('text-stone-700', className)}>{value}</span>;
    }
  }

  const preview = pickPreview(value);
  const oneLine = typeof value === 'string' ? value : JSON.stringify(value);
  const full =
    typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  const summary = preview ?? (oneLine.length <= 80 ? oneLine : oneLine.slice(0, 80) + '…');

  return (
    <div className={className}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="block max-w-full truncate text-left font-mono text-[11px] text-stone-600 hover:text-stone-900"
      >
        {open ? '▾ 收起' : summary}
      </button>
      {open && (
        <pre className="mt-1 max-h-64 overflow-auto rounded-md bg-stone-50 p-2 font-mono text-[11px] leading-relaxed text-stone-700">
          {full}
        </pre>
      )}
    </div>
  );
};

function pickPreview(value: unknown): string | null {
  if (value && typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    if (typeof obj.preview === 'string') return obj.preview.slice(0, 100);
    for (const v of Object.values(obj)) {
      if (
        v &&
        typeof v === 'object' &&
        typeof (v as Record<string, unknown>).preview === 'string'
      ) {
        return ((v as Record<string, unknown>).preview as string).slice(0, 100);
      }
    }
  }
  return null;
}

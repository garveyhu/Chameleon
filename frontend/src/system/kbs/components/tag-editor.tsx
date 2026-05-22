/** Tag 编辑器 —— chip 输入（回车 / 逗号添加，× 删除） */

import { X } from 'lucide-react';
import { useState } from 'react';

import { cn } from '@/core/lib/cn';

interface Props {
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

export const TagEditor = ({
  value,
  onChange,
  placeholder = '回车或逗号添加 tag',
  disabled,
  className,
}: Props) => {
  const [draft, setDraft] = useState('');

  const add = (raw: string) => {
    const t = raw.trim();
    if (!t || value.includes(t)) return;
    onChange([...value, t]);
  };

  const remove = (t: string) => {
    onChange(value.filter(v => v !== t));
  };

  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-1 rounded-md border border-stone-200 bg-white px-2 py-1.5',
        disabled && 'opacity-60',
        className,
      )}
    >
      {value.map(t => (
        <span
          key={t}
          className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11.5px] font-medium text-amber-700"
        >
          {t}
          {!disabled && (
            <button
              type="button"
              onClick={() => remove(t)}
              className="rounded-full p-0.5 hover:bg-amber-100"
              aria-label={`remove ${t}`}
            >
              <X className="h-2.5 w-2.5" />
            </button>
          )}
        </span>
      ))}
      <input
        type="text"
        className="min-w-[120px] flex-1 bg-transparent text-[12.5px] outline-none placeholder:text-stone-400"
        placeholder={value.length === 0 ? placeholder : ''}
        disabled={disabled}
        value={draft}
        onChange={e => setDraft(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            add(draft);
            setDraft('');
          } else if (e.key === 'Backspace' && !draft && value.length) {
            remove(value[value.length - 1]);
          }
        }}
        onBlur={() => {
          if (draft.trim()) {
            add(draft);
            setDraft('');
          }
        }}
      />
    </div>
  );
};

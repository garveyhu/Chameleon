/** InlineEditCell —— 表格内 hover-double-click 单元编辑 */

import { Check, Loader2, Pencil, X } from 'lucide-react';
import * as React from 'react';

import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';

interface InlineEditCellProps {
  value: string | number | null;
  type?: 'text' | 'number';
  placeholder?: string;
  min?: number;
  max?: number;
  step?: number;
  /** 必传：保存回调，返回 promise；onSave throw 时回滚 */
  onSave: (value: string | number) => Promise<void> | void;
  /** 显示态格式化 */
  format?: (v: string | number | null) => React.ReactNode;
  /** 不可编辑时只显示值 */
  readonly?: boolean;
  className?: string;
}

export const InlineEditCell: React.FC<InlineEditCellProps> = ({
  value,
  type = 'text',
  placeholder = '—',
  min,
  max,
  step,
  onSave,
  format,
  readonly = false,
  className,
}) => {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState<string>(String(value ?? ''));
  const [saving, setSaving] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const exitEdit = () => {
    setEditing(false);
    setDraft(String(value ?? ''));
  };

  const submit = async () => {
    if (saving) return;
    const parsed = type === 'number' ? Number(draft) : draft;
    if (type === 'number' && Number.isNaN(parsed)) {
      toast.error('请输入数字');
      return;
    }
    if (String(parsed) === String(value ?? '')) {
      setEditing(false);
      return;
    }
    try {
      setSaving(true);
      await onSave(parsed);
      setEditing(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  if (readonly) {
    return <span className={className}>{format ? format(value) : (value ?? placeholder)}</span>;
  }

  if (editing) {
    return (
      <span className={cn('inline-flex items-center gap-1', className)}>
        <input
          ref={inputRef}
          type={type}
          value={draft}
          min={min}
          max={max}
          step={step}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') submit();
            if (e.key === 'Escape') exitEdit();
          }}
          disabled={saving}
          className="h-6 w-full max-w-[140px] rounded border border-blue-300 bg-white px-1.5 text-[12px] outline-none ring-2 ring-blue-100"
        />
        {saving ? (
          <Loader2 className="h-3 w-3 animate-spin text-stone-400" />
        ) : (
          <>
            <button
              type="button"
              onClick={submit}
              className="rounded p-0.5 text-emerald-600 hover:bg-emerald-50"
            >
              <Check className="h-3 w-3" />
            </button>
            <button
              type="button"
              onClick={exitEdit}
              className="rounded p-0.5 text-stone-400 hover:bg-stone-100"
            >
              <X className="h-3 w-3" />
            </button>
          </>
        )}
      </span>
    );
  }

  return (
    <span
      className={cn(
        'group/inline inline-flex items-center gap-1 cursor-pointer',
        className,
      )}
      onDoubleClick={() => setEditing(true)}
      title="双击编辑"
    >
      <span>{format ? format(value) : (value ?? <span className="text-stone-400">{placeholder}</span>)}</span>
      <button
        type="button"
        onClick={e => {
          e.stopPropagation();
          setEditing(true);
        }}
        className="rounded p-0.5 opacity-0 transition group-hover/inline:opacity-100 hover:bg-stone-100"
        aria-label="编辑"
      >
        <Pencil className="h-3 w-3 text-stone-400" />
      </button>
    </span>
  );
};

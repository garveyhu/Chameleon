/** 日期 + 时间范围选择器（移植 waveflow-ui 范式）
 *
 * - Trigger 为按钮样式，显示已选范围（MM-DD HH:mm 简化）
 * - Popover 内两个 datetime-local 输入 + 今天/近24h/近7天/近30天 预设
 * - 传出 `YYYY-MM-DD HH:mm:ss` 字符串（后端可直接解析）
 */
import * as React from 'react';

import { Calendar, X } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/core/components/ui/popover';
import { cn } from '@/core/lib/cn';

export interface DateTimeRange {
  /** 'YYYY-MM-DD HH:mm:ss' */
  start?: string;
  end?: string;
}

export interface DateTimeRangePickerProps {
  value: DateTimeRange;
  onChange: (next: DateTimeRange) => void;
  placeholder?: string;
  triggerWidth?: number | string;
  size?: 'sm' | 'md';
  className?: string;
}

const toLocal = (s?: string) => {
  if (!s) return '';
  const m = s.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(?::(\d{2}))?/);
  if (!m) return '';
  return `${m[1]}T${m[2]}:${m[3] ?? '00'}`;
};

const fromLocal = (s: string): string | undefined => {
  if (!s) return undefined;
  const m = s.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(?::(\d{2}))?/);
  if (!m) return undefined;
  return `${m[1]} ${m[2]}:${m[3] ?? '00'}`;
};

const fmt = (d: Date) => {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
};

const presets: { label: string; range: () => DateTimeRange }[] = [
  {
    label: '今天',
    range: () => {
      const now = new Date();
      const start = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
      return { start: fmt(start), end: fmt(now) };
    },
  },
  {
    label: '近 24h',
    range: () => {
      const end = new Date();
      return { start: fmt(new Date(end.getTime() - 24 * 3600 * 1000)), end: fmt(end) };
    },
  },
  {
    label: '近 7 天',
    range: () => {
      const end = new Date();
      return { start: fmt(new Date(end.getTime() - 7 * 24 * 3600 * 1000)), end: fmt(end) };
    },
  },
  {
    label: '近 30 天',
    range: () => {
      const end = new Date();
      return { start: fmt(new Date(end.getTime() - 30 * 24 * 3600 * 1000)), end: fmt(end) };
    },
  },
];

const sizeClass = { sm: 'h-7 text-[12px]', md: 'h-8 text-[13px]' };

const displayRange = (v: DateTimeRange): string | null => {
  if (!v.start && !v.end) return null;
  const trim = (s?: string) => {
    if (!s) return '...';
    const m = s.match(/^\d{4}-(\d{2}-\d{2}) (\d{2}:\d{2})/);
    return m ? `${m[1]} ${m[2]}` : s;
  };
  return `${trim(v.start)} ~ ${trim(v.end)}`;
};

export const DateTimeRangePicker: React.FC<DateTimeRangePickerProps> = ({
  value,
  onChange,
  placeholder = '选择时间范围',
  triggerWidth = 190,
  size = 'sm',
  className,
}) => {
  const [open, setOpen] = React.useState(false);
  const [localStart, setLocalStart] = React.useState(toLocal(value.start));
  const [localEnd, setLocalEnd] = React.useState(toLocal(value.end));

  // 打开时把外部值灌入本地编辑态（避免 effect 同步 setState）
  const onOpenChange = (o: boolean) => {
    if (o) {
      setLocalStart(toLocal(value.start));
      setLocalEnd(toLocal(value.end));
    }
    setOpen(o);
  };

  const display = displayRange(value);

  const apply = () => {
    onChange({ start: fromLocal(localStart), end: fromLocal(localEnd) });
    setOpen(false);
  };
  const clear = () => {
    setLocalStart('');
    setLocalEnd('');
    onChange({});
  };

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <button
          type="button"
          style={{ width: triggerWidth }}
          className={cn(
            'flex items-center gap-2 rounded-md border border-stone-300 bg-white px-2.5 transition outline-none',
            'hover:border-stone-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100',
            sizeClass[size],
            className,
          )}
        >
          <Calendar className="h-3.5 w-3.5 shrink-0 text-stone-400" />
          <span
            className={cn(
              'tnum flex-1 truncate text-left font-mono',
              display ? 'text-stone-800' : '!font-sans text-stone-400',
            )}
          >
            {display ?? placeholder}
          </span>
          {display ? (
            <span
              role="button"
              tabIndex={0}
              onClick={e => {
                e.stopPropagation();
                clear();
              }}
              onKeyDown={e => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.stopPropagation();
                  e.preventDefault();
                  clear();
                }
              }}
              className="rounded p-0.5 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
              aria-label="清除"
            >
              <X className="h-3 w-3" />
            </span>
          ) : null}
        </button>
      </PopoverTrigger>
      <PopoverContent className="!w-[340px]" align="start">
        <div className="space-y-2.5">
          <div>
            <div className="mb-1 text-[11px] text-stone-500">开始时间</div>
            <input
              type="datetime-local"
              step="1"
              value={localStart}
              onChange={e => setLocalStart(e.target.value)}
              className="h-7 w-full rounded-md border border-stone-300 bg-white px-2 text-[12px] transition outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            />
          </div>
          <div>
            <div className="mb-1 text-[11px] text-stone-500">结束时间</div>
            <input
              type="datetime-local"
              step="1"
              value={localEnd}
              onChange={e => setLocalEnd(e.target.value)}
              className="h-7 w-full rounded-md border border-stone-300 bg-white px-2 text-[12px] transition outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            />
          </div>
          <div className="flex flex-wrap gap-1">
            {presets.map(p => (
              <button
                key={p.label}
                type="button"
                onClick={() => {
                  const r = p.range();
                  setLocalStart(toLocal(r.start));
                  setLocalEnd(toLocal(r.end));
                  onChange(r);
                  setOpen(false);
                }}
                className="rounded border border-stone-200 bg-white px-2 py-0.5 text-[11px] text-stone-600 transition hover:border-stone-400 hover:text-stone-900"
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="flex justify-end gap-1.5 border-t border-stone-100 pt-2.5">
            <Button variant="ghost" size="sm" onClick={clear}>
              清空
            </Button>
            <Button variant="primary" size="sm" onClick={apply}>
              应用
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
};

/** DateRangePicker —— preset + 自定义日历区间选择 */

import { Calendar as CalendarIcon, ChevronDown } from 'lucide-react';
import * as React from 'react';

import { cn } from '@/core/lib/cn';

export interface DateRange {
  from: Date;
  to: Date;
}

interface Preset {
  label: string;
  range: () => DateRange;
}

const startOfDay = (d: Date): Date => {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
};

const endOfDay = (d: Date): Date => {
  const x = new Date(d);
  x.setHours(23, 59, 59, 999);
  return x;
};

const today = (): Date => new Date();

const PRESETS: Preset[] = [
  {
    label: '今天',
    range: () => ({ from: startOfDay(today()), to: endOfDay(today()) }),
  },
  {
    label: '昨天',
    range: () => {
      const y = new Date();
      y.setDate(y.getDate() - 1);
      return { from: startOfDay(y), to: endOfDay(y) };
    },
  },
  {
    label: '近 7 天',
    range: () => {
      const from = new Date();
      from.setDate(from.getDate() - 6);
      return { from: startOfDay(from), to: endOfDay(today()) };
    },
  },
  {
    label: '近 30 天',
    range: () => {
      const from = new Date();
      from.setDate(from.getDate() - 29);
      return { from: startOfDay(from), to: endOfDay(today()) };
    },
  },
  {
    label: '本月',
    range: () => {
      const t = today();
      const from = new Date(t.getFullYear(), t.getMonth(), 1);
      return { from: startOfDay(from), to: endOfDay(today()) };
    },
  },
  {
    label: '上月',
    range: () => {
      const t = today();
      const from = new Date(t.getFullYear(), t.getMonth() - 1, 1);
      const to = new Date(t.getFullYear(), t.getMonth(), 0);
      return { from: startOfDay(from), to: endOfDay(to) };
    },
  },
];

const formatDate = (d: Date): string => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
};

const toInputValue = (d: Date): string => formatDate(d);
const fromInputValue = (s: string, eod = false): Date => {
  const [y, m, day] = s.split('-').map(Number);
  const d = new Date(y, m - 1, day);
  return eod ? endOfDay(d) : startOfDay(d);
};

interface DateRangePickerProps {
  value: DateRange;
  onChange: (range: DateRange) => void;
  className?: string;
}

export const DateRangePicker: React.FC<DateRangePickerProps> = ({ value, onChange, className }) => {
  const [open, setOpen] = React.useState(false);
  const [customFrom, setCustomFrom] = React.useState(toInputValue(value.from));
  const [customTo, setCustomTo] = React.useState(toInputValue(value.to));
  const wrapperRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const label = `${formatDate(value.from)} ~ ${formatDate(value.to)}`;

  const applyPreset = (p: Preset) => {
    const r = p.range();
    onChange(r);
    setCustomFrom(toInputValue(r.from));
    setCustomTo(toInputValue(r.to));
    setOpen(false);
  };

  const applyCustom = () => {
    try {
      const from = fromInputValue(customFrom, false);
      const to = fromInputValue(customTo, true);
      if (from > to) return;
      onChange({ from, to });
      setOpen(false);
    } catch {
      /* noop */
    }
  };

  return (
    <div ref={wrapperRef} className={cn('relative inline-block', className)}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="inline-flex h-7 items-center gap-2 rounded-md border border-stone-200 bg-paper px-2.5 text-[12px] text-stone-700 hover:border-stone-300"
      >
        <CalendarIcon className="h-3.5 w-3.5 text-stone-400" strokeWidth={1.75} />
        <span className="tnum">{label}</span>
        <ChevronDown className="h-3 w-3 text-stone-400" />
      </button>
      {open ? (
        <div className="absolute right-0 z-30 mt-1.5 flex w-[460px] rounded-lg border border-stone-200 bg-paper shadow-pop">
          <ul className="w-32 shrink-0 border-r border-stone-100 p-2">
            {PRESETS.map(p => (
              <li key={p.label}>
                <button
                  type="button"
                  onClick={() => applyPreset(p)}
                  className="w-full rounded-md px-2 py-1.5 text-left text-[12px] text-stone-600 hover:bg-stone-100 hover:text-stone-900"
                >
                  {p.label}
                </button>
              </li>
            ))}
          </ul>
          <div className="flex-1 p-3">
            <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-stone-400">
              自定义
            </div>
            <div className="space-y-2">
              <label className="block text-[12px] text-stone-600">
                开始
                <input
                  type="date"
                  value={customFrom}
                  max={customTo}
                  onChange={e => setCustomFrom(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-stone-200 bg-paper px-2 py-1 text-[12px] outline-none focus:border-blue-500"
                />
              </label>
              <label className="block text-[12px] text-stone-600">
                结束
                <input
                  type="date"
                  value={customTo}
                  min={customFrom}
                  onChange={e => setCustomTo(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-stone-200 bg-paper px-2 py-1 text-[12px] outline-none focus:border-blue-500"
                />
              </label>
              <button
                type="button"
                onClick={applyCustom}
                className="mt-2 w-full rounded-md bg-blue-600 px-2 py-1.5 text-[12px] font-medium text-white hover:bg-blue-700"
              >
                应用
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};

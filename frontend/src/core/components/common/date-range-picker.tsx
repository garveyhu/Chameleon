/** DateRangePicker —— preset 侧栏 + 自绘月历区间选择（Popover）
 *
 * 对外 API 保持 { from: Date, to: Date }（仪表盘等沿用）；内部用共享 MonthCalendar。
 */
import * as React from 'react';

import dayjs, { type Dayjs } from 'dayjs';
import { Calendar as CalendarIcon, ChevronDown } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { MonthCalendar } from '@/core/components/ui/month-calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/core/components/ui/popover';
import { cn } from '@/core/lib/cn';

export interface DateRange {
  from: Date;
  to: Date;
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
const fmt = (d: Date): string => dayjs(d).format('YYYY-MM-DD');

interface Preset {
  label: string;
  range: () => DateRange;
}

const PRESETS: Preset[] = [
  { label: '今天', range: () => ({ from: startOfDay(new Date()), to: endOfDay(new Date()) }) },
  {
    label: '昨天',
    range: () => {
      const y = dayjs().subtract(1, 'day');
      return { from: startOfDay(y.toDate()), to: endOfDay(y.toDate()) };
    },
  },
  {
    label: '近 7 天',
    range: () => ({
      from: startOfDay(dayjs().subtract(6, 'day').toDate()),
      to: endOfDay(new Date()),
    }),
  },
  {
    label: '近 30 天',
    range: () => ({
      from: startOfDay(dayjs().subtract(29, 'day').toDate()),
      to: endOfDay(new Date()),
    }),
  },
  {
    label: '本月',
    range: () => ({
      from: startOfDay(dayjs().startOf('month').toDate()),
      to: endOfDay(new Date()),
    }),
  },
  {
    label: '上月',
    range: () => {
      const m = dayjs().subtract(1, 'month');
      return {
        from: startOfDay(m.startOf('month').toDate()),
        to: endOfDay(m.endOf('month').toDate()),
      };
    },
  },
];

interface DateRangePickerProps {
  value: DateRange;
  onChange: (range: DateRange) => void;
  className?: string;
}

export const DateRangePicker: React.FC<DateRangePickerProps> = ({ value, onChange, className }) => {
  const [open, setOpen] = React.useState(false);
  const [start, setStart] = React.useState<Dayjs | null>(dayjs(value.from));
  const [end, setEnd] = React.useState<Dayjs | null>(dayjs(value.to));

  const onOpenChange = (o: boolean) => {
    if (o) {
      setStart(dayjs(value.from));
      setEnd(dayjs(value.to));
    }
    setOpen(o);
  };

  const pick = (d: Dayjs) => {
    if (!start || (start && end)) {
      setStart(d);
      setEnd(null);
    } else if (d.isBefore(start, 'day')) {
      setStart(d);
    } else {
      setEnd(d);
    }
  };

  const apply = () => {
    if (!start) return;
    const e = end ?? start;
    onChange({ from: startOfDay(start.toDate()), to: endOfDay(e.toDate()) });
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            'bg-paper inline-flex h-7 items-center gap-2 rounded-md border border-stone-200 px-2.5 text-[12px] text-stone-700 hover:border-stone-300',
            className,
          )}
        >
          <CalendarIcon className="h-3.5 w-3.5 text-stone-400" strokeWidth={1.75} />
          <span className="tnum">
            {fmt(value.from)} ~ {fmt(value.to)}
          </span>
          <ChevronDown className="h-3 w-3 text-stone-400" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="!w-auto !p-0" align="end">
        <div className="flex">
          <ul className="w-24 shrink-0 space-y-0.5 border-r border-stone-100 p-2">
            {PRESETS.map(p => (
              <li key={p.label}>
                <button
                  type="button"
                  onClick={() => {
                    onChange(p.range());
                    setOpen(false);
                  }}
                  className="w-full rounded-md px-2 py-1.5 text-left text-[12px] text-stone-600 transition hover:bg-stone-100 hover:text-stone-900"
                >
                  {p.label}
                </button>
              </li>
            ))}
          </ul>
          <div className="p-3">
            <MonthCalendar start={start} end={end} onPick={pick} />
            <div className="mt-2 flex items-center justify-between border-t border-stone-100 pt-2">
              <span className="font-mono text-[11px] text-stone-500">
                {start
                  ? `${start.format('MM-DD')} ~ ${(end ?? start).format('MM-DD')}`
                  : '点选起止日期'}
              </span>
              <Button variant="primary" size="sm" onClick={apply} disabled={!start}>
                应用
              </Button>
            </div>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
};

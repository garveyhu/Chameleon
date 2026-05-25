/** 日期范围选择器 —— 自绘日历（dayjs），现代卡片风
 *
 * - Trigger 按钮显示已选范围（MM-DD ~ MM-DD），可一键清除
 * - Popover 内：月历（点两次选起止，区间高亮）+ 今天/近7天/近30天 预设 + 清空/应用
 * - 传出 `YYYY-MM-DD HH:mm:ss`（起 00:00:00、止 23:59:59），后端可直接解析
 */
import * as React from 'react';

import dayjs, { type Dayjs } from 'dayjs';
import { Calendar as CalIcon, ChevronLeft, ChevronRight, X } from 'lucide-react';

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

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日'];
const sizeClass = { sm: 'h-7 text-[12px]', md: 'h-8 text-[13px]' };

const toStart = (d: Dayjs) => d.format('YYYY-MM-DD') + ' 00:00:00';
const toEnd = (d: Dayjs) => d.format('YYYY-MM-DD') + ' 23:59:59';

const displayRange = (v: DateTimeRange): string | null => {
  if (!v.start && !v.end) return null;
  const trim = (s?: string) => (s ? s.slice(5, 10) : '…');
  return `${trim(v.start)} ~ ${trim(v.end)}`;
};

/** 月历：周一为首列，点击选起止（两次），区间高亮 */
const MonthCalendar: React.FC<{
  start: Dayjs | null;
  end: Dayjs | null;
  onPick: (d: Dayjs) => void;
}> = ({ start, end, onPick }) => {
  const [view, setView] = React.useState<Dayjs>(start ?? dayjs());
  const first = view.startOf('month');
  // 周一为第 0 列：dayjs day() 周日=0 → 映射到 6
  const leading = (first.day() + 6) % 7;
  const gridStart = first.subtract(leading, 'day');
  const days = Array.from({ length: 42 }, (_, i) => gridStart.add(i, 'day'));
  const inRange = (d: Dayjs) =>
    start &&
    end &&
    (d.isSame(start, 'day') || d.isSame(end, 'day') || (d.isAfter(start) && d.isBefore(end)));
  const isEnd = (d: Dayjs) => (start && d.isSame(start, 'day')) || (end && d.isSame(end, 'day'));

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between px-1">
        <button
          type="button"
          onClick={() => setView(view.subtract(1, 'month'))}
          className="rounded p-1 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
        <span className="text-[12.5px] font-medium text-stone-700">
          {view.format('YYYY 年 M 月')}
        </span>
        <button
          type="button"
          onClick={() => setView(view.add(1, 'month'))}
          className="rounded p-1 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="grid grid-cols-7 gap-y-0.5">
        {WEEKDAYS.map(w => (
          <div key={w} className="py-1 text-center text-[10.5px] text-stone-400">
            {w}
          </div>
        ))}
        {days.map(d => {
          const out = d.month() !== view.month();
          const today = d.isSame(dayjs(), 'day');
          const sel = isEnd(d);
          const range = inRange(d) && !sel;
          return (
            <button
              key={d.format('YYYY-MM-DD')}
              type="button"
              onClick={() => onPick(d)}
              className={cn(
                'mx-auto flex h-7 w-7 items-center justify-center rounded-md text-[12px] transition',
                out ? 'text-stone-300' : 'text-stone-700',
                range && 'bg-blue-50 text-blue-700',
                sel && 'bg-blue-600 font-medium text-white hover:bg-blue-600',
                !sel && !range && 'hover:bg-stone-100',
                today && !sel && 'font-semibold text-blue-600',
              )}
            >
              {d.date()}
            </button>
          );
        })}
      </div>
    </div>
  );
};

export const DateTimeRangePicker: React.FC<DateTimeRangePickerProps> = ({
  value,
  onChange,
  placeholder = '选择时间范围',
  triggerWidth = 200,
  size = 'sm',
  className,
}) => {
  const [open, setOpen] = React.useState(false);
  const [start, setStart] = React.useState<Dayjs | null>(value.start ? dayjs(value.start) : null);
  const [end, setEnd] = React.useState<Dayjs | null>(value.end ? dayjs(value.end) : null);

  const onOpenChange = (o: boolean) => {
    if (o) {
      setStart(value.start ? dayjs(value.start) : null);
      setEnd(value.end ? dayjs(value.end) : null);
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

  const applyPreset = (days: number) => {
    const e = dayjs();
    const s = e.subtract(days, 'day');
    onChange({ start: toStart(s), end: toEnd(e) });
    setOpen(false);
  };

  const apply = () => {
    onChange({
      start: start ? toStart(start) : undefined,
      end: (end ?? start) ? toEnd(end ?? (start as Dayjs)) : undefined,
    });
    setOpen(false);
  };

  const clear = () => {
    setStart(null);
    setEnd(null);
    onChange({});
  };

  const display = displayRange(value);

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
          <CalIcon className="h-3.5 w-3.5 shrink-0 text-stone-400" />
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
      <PopoverContent className="!w-[280px]" align="start">
        <MonthCalendar start={start} end={end} onPick={pick} />
        <div className="mt-2 flex items-center justify-between border-t border-stone-100 pt-2">
          <div className="flex gap-1">
            {[
              { label: '今天', days: 0 },
              { label: '近 7 天', days: 7 },
              { label: '近 30 天', days: 30 },
            ].map(p => (
              <button
                key={p.label}
                type="button"
                onClick={() => applyPreset(p.days)}
                className="rounded border border-stone-200 px-1.5 py-0.5 text-[11px] text-stone-600 transition hover:border-stone-400 hover:text-stone-900"
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="flex gap-1">
            <Button variant="ghost" size="sm" onClick={clear}>
              清空
            </Button>
            <Button variant="primary" size="sm" onClick={apply} disabled={!start}>
              应用
            </Button>
          </div>
        </div>
        {start ? (
          <div className="mt-1.5 text-center font-mono text-[11px] text-stone-500">
            {start.format('MM-DD')} ~ {(end ?? start).format('MM-DD')}
          </div>
        ) : (
          <div className="mt-1.5 text-center text-[11px] text-stone-400">点选起止日期</div>
        )}
      </PopoverContent>
    </Popover>
  );
};

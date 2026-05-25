/** 月历 —— 周一为首列，点两次选起止区间，区间高亮（dayjs） */
import * as React from 'react';

import dayjs, { type Dayjs } from 'dayjs';
import { ChevronLeft, ChevronRight } from 'lucide-react';

import { cn } from '@/core/lib/cn';

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日'];

export interface MonthCalendarProps {
  start: Dayjs | null;
  end: Dayjs | null;
  onPick: (d: Dayjs) => void;
}

export const MonthCalendar: React.FC<MonthCalendarProps> = ({ start, end, onPick }) => {
  const [view, setView] = React.useState<Dayjs>(start ?? dayjs());
  const first = view.startOf('month');
  const leading = (first.day() + 6) % 7; // 周一为第 0 列
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

/** MiniStat —— 紧凑指标卡：图标 + 大数字 + 标签。
 *
 * 比 StatTile 轻，用于列表页顶部成排展示概览（"仪表盘感"），不抢主体卡片风头。
 */

import type { ComponentType } from 'react';

import { cn } from '@/core/lib/cn';

export type MiniStatTone =
  | 'primary'
  | 'success'
  | 'warning'
  | 'danger'
  | 'violet'
  | 'sky'
  | 'neutral';

const TONE: Record<MiniStatTone, string> = {
  primary: 'bg-primary-50 text-primary-600',
  success: 'bg-emerald-50 text-emerald-600',
  warning: 'bg-amber-50 text-amber-600',
  danger: 'bg-red-50 text-red-600',
  violet: 'bg-violet-50 text-violet-600',
  sky: 'bg-sky-50 text-sky-600',
  neutral: 'bg-stone-100 text-stone-500',
};

interface Props {
  label: string;
  value: string | number;
  icon: ComponentType<{ className?: string }>;
  tone?: MiniStatTone;
}

export const MiniStat = ({ label, value, icon: Icon, tone = 'neutral' }: Props) => (
  <div className="flex items-center gap-3 rounded-xl border border-stone-200 bg-[var(--color-paper)] px-4 py-3">
    <div className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-lg', TONE[tone])}>
      <Icon className="h-[18px] w-[18px]" />
    </div>
    <div className="min-w-0">
      <div className="tnum font-mono text-[19px] leading-none font-semibold text-stone-900">
        {value}
      </div>
      <div className="mt-1 truncate text-[11px] text-stone-500">{label}</div>
    </div>
  </div>
);

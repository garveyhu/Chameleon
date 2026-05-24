/** StatTile —— 指标大数字卡：label / value / hint / 环比 delta / 图标。
 *
 * 统一 dashboard、cost、eval 等页面此前各自内联的 stat 卡。
 * deltaInverse 用于"越低越好"的指标（如成本）：上升显红、下降显绿。
 */

import { TrendingDown, TrendingUp } from 'lucide-react';
import type { ComponentType } from 'react';

import { cn } from '@/core/lib/cn';

export type StatTone = 'primary' | 'success' | 'warning' | 'danger' | 'neutral';

const TONE_CHIP: Record<StatTone, string> = {
  primary: 'bg-primary-50 text-primary-600',
  success: 'bg-emerald-50 text-emerald-600',
  warning: 'bg-amber-50 text-amber-600',
  danger: 'bg-red-50 text-red-600',
  neutral: 'bg-stone-100 text-stone-500',
};

interface StatTileProps {
  label: string;
  /** 已格式化的展示值 */
  value: string;
  hint?: string;
  /** 环比变化（小数，0.12 = +12%）；null/undefined 不显示 */
  delta?: number | null;
  /** 上升视为"坏"（红），用于成本等越低越好的指标 */
  deltaInverse?: boolean;
  icon?: ComponentType<{ className?: string }>;
  tone?: StatTone;
  loading?: boolean;
  className?: string;
}

export const StatTile = ({
  label,
  value,
  hint,
  delta,
  deltaInverse,
  icon: Icon,
  tone = 'primary',
  loading,
  className,
}: StatTileProps) => {
  const hasDelta = delta != null && Number.isFinite(delta);
  const up = hasDelta && (delta as number) > 0;
  const down = hasDelta && (delta as number) < 0;
  const good = deltaInverse ? down : up;
  const deltaColor =
    !hasDelta || delta === 0
      ? 'text-stone-400'
      : good
        ? 'text-emerald-600'
        : 'text-red-600';

  return (
    <div
      className={cn(
        'flex items-start justify-between rounded-xl border border-stone-200 bg-[var(--color-paper)] p-5',
        className,
      )}
    >
      <div className="min-w-0">
        <div className="text-xs text-stone-500">{label}</div>
        <div className="mt-2 truncate font-mono text-2xl tracking-tight text-stone-900">
          {loading ? '—' : value}
        </div>
        <div className="mt-1 flex items-center gap-2 text-[11px]">
          {hint && <span className="truncate text-stone-400">{hint}</span>}
          {hasDelta && (
            <span className={cn('inline-flex shrink-0 items-center gap-0.5 font-medium', deltaColor)}>
              {up ? (
                <TrendingUp className="h-3 w-3" />
              ) : down ? (
                <TrendingDown className="h-3 w-3" />
              ) : null}
              {up ? '+' : ''}
              {((delta as number) * 100).toFixed(1)}%
            </span>
          )}
        </div>
      </div>
      {Icon && (
        <div
          className={cn(
            'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
            TONE_CHIP[tone],
          )}
        >
          <Icon className="h-5 w-5" />
        </div>
      )}
    </div>
  );
};

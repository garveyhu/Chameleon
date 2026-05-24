/** StatusBadge —— 语义状态徽标，带状态点（可选脉冲动画）。
 *
 * 与 Badge 互补：Badge 是纯文字标签，StatusBadge 强调"状态"语义（成功/失败/运行中），
 * 用于日志、任务、健康度等场景。pulse 为活跃态加 ping 动画（如运行中/排队中）。
 */

import * as React from 'react';

import { cn } from '@/core/lib/cn';

export type StatusTone =
  | 'success'
  | 'error'
  | 'warning'
  | 'info'
  | 'running'
  | 'neutral';

const TONE: Record<StatusTone, { dot: string; pill: string }> = {
  success: { dot: 'bg-emerald-500', pill: 'bg-emerald-50 text-emerald-700' },
  error: { dot: 'bg-red-500', pill: 'bg-red-50 text-red-700' },
  warning: { dot: 'bg-amber-500', pill: 'bg-amber-50 text-amber-700' },
  info: { dot: 'bg-sky-500', pill: 'bg-sky-50 text-sky-700' },
  running: { dot: 'bg-sky-500', pill: 'bg-sky-50 text-sky-700' },
  neutral: { dot: 'bg-stone-400', pill: 'bg-stone-100 text-stone-600' },
};

interface StatusBadgeProps {
  tone: StatusTone;
  children: React.ReactNode;
  /** 活跃态加脉冲（ping）动画，如运行中 / 排队中 */
  pulse?: boolean;
  className?: string;
}

export const StatusBadge = ({ tone, children, pulse, className }: StatusBadgeProps) => {
  const c = TONE[tone];
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-2 py-0.5 text-[11px] font-medium',
        c.pill,
        className,
      )}
    >
      <span className="relative flex h-1.5 w-1.5">
        {pulse && (
          <span
            className={cn(
              'absolute inline-flex h-full w-full animate-ping rounded-full opacity-75',
              c.dot,
            )}
          />
        )}
        <span className={cn('relative inline-flex h-1.5 w-1.5 rounded-full', c.dot)} />
      </span>
      {children}
    </span>
  );
};

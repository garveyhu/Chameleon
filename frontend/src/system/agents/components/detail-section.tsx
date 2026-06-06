/** 应用详情各 tab 共用的高质感区块卡 —— 统一圆角/边框/阴影/标题栏视觉语言。 */
import type { ComponentType, ReactNode } from 'react';

import { cn } from '@/core/lib/cn';

interface Props {
  icon?: ComponentType<{ className?: string }>;
  title?: ReactNode;
  desc?: ReactNode;
  /** 标题栏右侧（操作 / 计数等） */
  action?: ReactNode;
  /** 不要内边距（如内嵌表格自带 padding） */
  flush?: boolean;
  className?: string;
  children: ReactNode;
}

export const DetailSection = ({
  icon: Icon,
  title,
  desc,
  action,
  flush,
  className,
  children,
}: Props) => (
  <section className="overflow-hidden rounded-2xl border border-stone-200 bg-[var(--color-paper)] shadow-sm">
    {(title || action) && (
      <div className="flex items-center justify-between gap-3 border-b border-stone-100 bg-stone-50/50 px-5 py-3">
        <div className="flex items-center gap-2 min-w-0">
          {Icon && (
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white text-stone-500 shadow-sm">
              <Icon className="h-4 w-4" />
            </span>
          )}
          <div className="min-w-0">
            {title && (
              <div className="truncate text-[13px] font-semibold text-stone-800">{title}</div>
            )}
            {desc && <div className="truncate text-[11px] text-stone-400">{desc}</div>}
          </div>
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
    )}
    <div className={cn(!flush && 'p-5', className)}>{children}</div>
  </section>
);

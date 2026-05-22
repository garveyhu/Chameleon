/** EmptyState —— 空状态展示（图标 + 标题 + 描述 + 可选 action） */

import * as React from 'react';

import { cn } from '@/core/lib/cn';

interface EmptyStateProps {
  icon?: React.ReactNode;
  title?: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  /** 紧凑模式（表格内空状态用），默认 false */
  compact?: boolean;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title = '暂无数据',
  description,
  action,
  className,
  compact = false,
}) => (
  <div
    className={cn(
      'flex flex-col items-center justify-center text-center',
      compact ? 'gap-1.5 py-2' : 'gap-3 py-10',
      className,
    )}
  >
    {icon ? (
      <div
        className={cn(
          'text-stone-300',
          compact ? '[&>svg]:h-7 [&>svg]:w-7' : '[&>svg]:h-12 [&>svg]:w-12',
        )}
      >
        {icon}
      </div>
    ) : null}
    {title ? (
      <div
        className={cn(
          'font-medium text-stone-600',
          compact ? 'text-[12.5px]' : 'text-[14px]',
        )}
      >
        {title}
      </div>
    ) : null}
    {description ? (
      <div
        className={cn(
          'max-w-sm leading-relaxed text-stone-400',
          compact ? 'text-[11.5px]' : 'text-[12.5px]',
        )}
      >
        {description}
      </div>
    ) : null}
    {action ? <div className={compact ? 'mt-1' : 'mt-2'}>{action}</div> : null}
  </div>
);

/** Skeleton —— shimmer 占位件，配合 .skeleton 全局 class */

import * as React from 'react';

import { cn } from '@/core/lib/cn';

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  width?: number | string;
  height?: number | string;
  rounded?: 'none' | 'sm' | 'md' | 'lg' | 'full';
}

const ROUNDED: Record<NonNullable<SkeletonProps['rounded']>, string> = {
  none: 'rounded-none',
  sm: 'rounded-sm',
  md: 'rounded-md',
  lg: 'rounded-lg',
  full: 'rounded-full',
};

export const Skeleton: React.FC<SkeletonProps> = ({
  width,
  height,
  rounded = 'md',
  className,
  style,
  ...rest
}) => (
  <div
    className={cn('skeleton', ROUNDED[rounded], className)}
    style={{ width, height, ...style }}
    {...rest}
  />
);

interface SkeletonTextProps {
  lines?: number;
  /** 每行高度 px */
  lineHeight?: number;
  /** 行间距 px */
  gap?: number;
  /** 最后一行宽度比例（0-1） */
  lastLineWidth?: number;
  className?: string;
}

export const SkeletonText: React.FC<SkeletonTextProps> = ({
  lines = 3,
  lineHeight = 10,
  gap = 8,
  lastLineWidth = 0.6,
  className,
}) => (
  <div className={cn('flex flex-col', className)} style={{ gap }}>
    {Array.from({ length: lines }).map((_, i) => (
      <Skeleton
        key={i}
        height={lineHeight}
        width={i === lines - 1 ? `${lastLineWidth * 100}%` : '100%'}
        rounded="full"
      />
    ))}
  </div>
);

interface SkeletonCardProps {
  /** 是否含 avatar 圆形头部 */
  avatar?: boolean;
  /** 行数 */
  lines?: number;
  className?: string;
}

export const SkeletonCard: React.FC<SkeletonCardProps> = ({
  avatar = false,
  lines = 3,
  className,
}) => (
  <div
    className={cn(
      'flex flex-col gap-3 rounded-lg border border-stone-200/60 bg-paper p-4',
      className,
    )}
  >
    {avatar ? (
      <div className="flex items-center gap-3">
        <Skeleton width={36} height={36} rounded="full" />
        <div className="flex-1">
          <Skeleton height={10} width="40%" rounded="full" />
        </div>
      </div>
    ) : null}
    <SkeletonText lines={lines} />
  </div>
);

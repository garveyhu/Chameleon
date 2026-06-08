/** 霓虹感 loading —— 渐变辉光旋转环 + 流光文字。长耗时 AI 生成任务（评测 / 分析 / 扩样 /
 *  优化 / 生图…）通用，按场景选 size。样式见 assets/styles/theme.css 的 .neon-loader__*。 */

import type { CSSProperties } from 'react';

import { cn } from '@/core/lib/cn';

export type NeonLoaderSize = 'xs' | 'sm' | 'md' | 'lg';

// d=环直径，t=环厚，text=默认文案字号
const SIZES: Record<NeonLoaderSize, { d: number; t: number; text: string }> = {
  xs: { d: 12, t: 2, text: 'text-[11px]' },
  sm: { d: 14, t: 2.25, text: 'text-[11.5px]' },
  md: { d: 16, t: 2.5, text: 'text-[12px]' },
  lg: { d: 24, t: 3.25, text: 'text-[13.5px]' },
};

interface NeonLoaderProps {
  /** 右侧流光文案（如「评测进行中…」）。省略则只显示旋转环。 */
  label?: string;
  /** 场景尺寸：xs 内联按钮 / sm 紧凑 / md 默认 / lg 大面板 */
  size?: NeonLoaderSize;
  /** 容器加一圈柔和辉光底 + 呼吸（独立成块时更有氛围；内联可不开） */
  glow?: boolean;
  className?: string;
  /** 覆盖文案字号 */
  textClassName?: string;
}

export const NeonLoader = ({
  label,
  size = 'md',
  glow,
  className,
  textClassName,
}: NeonLoaderProps) => {
  const s = SIZES[size];
  const ringStyle = {
    '--neon-d': `${s.d}px`,
    '--neon-t': `${s.t}px`,
  } as CSSProperties;
  return (
    <div
      className={cn(
        'inline-flex items-center gap-2 rounded-lg',
        glow && 'neon-loader--glow px-3 py-1.5',
        className,
      )}
    >
      <span className="neon-loader__ring shrink-0" style={ringStyle} aria-hidden />
      {label && (
        <span
          className={cn(
            'neon-loader__text font-medium tracking-wide',
            textClassName ?? s.text,
          )}
        >
          {label}
        </span>
      )}
    </div>
  );
};

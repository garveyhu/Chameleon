/** 分段切换控件 —— 全站表单「二选一 / 多选一」切换统一用它。
 *  舒适内边距（不贴字），选中态深底白字，pill 滑块感。 */

import type { ReactNode } from 'react';

import { cn } from '@/core/lib/cn';

export interface SegmentedOption<T extends string> {
  value: T;
  label: ReactNode;
  /** 可选：禁用该项 */
  disabled?: boolean;
}

interface SegmentedControlProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  options: SegmentedOption<T>[];
  /** sm 用于行内紧凑场景；md（默认）用于表单 */
  size?: 'sm' | 'md';
  className?: string;
}

export const SegmentedControl = <T extends string>({
  value,
  onChange,
  options,
  size = 'md',
  className,
}: SegmentedControlProps<T>) => (
  <div
    role="tablist"
    className={cn(
      'inline-flex items-center gap-1.5 rounded-xl border border-stone-200 bg-stone-100/70 p-1.5',
      className,
    )}
  >
    {options.map(opt => {
      const active = opt.value === value;
      return (
        <button
          key={opt.value}
          type="button"
          role="tab"
          aria-selected={active}
          disabled={opt.disabled}
          onClick={() => !opt.disabled && onChange(opt.value)}
          className={cn(
            'rounded-lg font-medium leading-none transition-colors disabled:cursor-not-allowed disabled:opacity-40',
            size === 'sm'
              ? 'px-3.5 py-2 text-[12px]'
              : 'px-5 py-2.5 text-[12.5px]',
            active
              ? 'bg-stone-800 text-white shadow-sm'
              : 'text-stone-500 hover:bg-white hover:text-stone-800',
          )}
        >
          {opt.label}
        </button>
      );
    })}
  </div>
);

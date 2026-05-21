/** Input —— waveflow 风格复刻
 *
 * h-8 + 13px + 蓝聚焦 + 错误态红边
 */

import * as React from 'react';

import { cn } from '@/core/lib/cn';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  /** 错误态：红边 + 红 focus ring */
  error?: boolean;
  /** 用 mono 字体（id / cron / 数字） */
  mono?: boolean;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type = 'text', error, mono, ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        'h-8 w-full rounded-md border border-stone-300 bg-white px-3 text-[13px] outline-none transition placeholder:text-stone-400',
        'focus:border-blue-500 focus:ring-2 focus:ring-blue-100',
        'disabled:cursor-not-allowed disabled:bg-stone-100 disabled:text-stone-500',
        error && 'border-red-500 focus:border-red-500 focus:ring-red-100',
        mono && 'font-mono tnum',
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = 'Input';

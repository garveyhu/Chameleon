/** Textarea —— waveflow 紧凑风格 */

import * as React from 'react';

import { cn } from '@/core/lib/cn';

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      'w-full min-h-[72px] rounded-md border border-stone-300 bg-white px-3 py-1.5 text-[13px] outline-none transition placeholder:text-stone-400',
      'focus:border-blue-500 focus:ring-2 focus:ring-blue-100',
      'disabled:cursor-not-allowed disabled:bg-stone-100 disabled:text-stone-500',
      className,
    )}
    {...props}
  />
));
Textarea.displayName = 'Textarea';

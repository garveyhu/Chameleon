/** Tooltip —— 全站统一悬浮提示（waveflow 风格暗底） */

import * as TooltipPrimitive from '@radix-ui/react-tooltip';
import * as React from 'react';

import { cn } from '@/core/lib/cn';

export const TooltipProvider = TooltipPrimitive.Provider;
export const TooltipRoot = TooltipPrimitive.Root;
export const TooltipTrigger = TooltipPrimitive.Trigger;
export const TooltipPortal = TooltipPrimitive.Portal;

export const TooltipContent = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(({ className, sideOffset = 6, ...props }, ref) => (
  <TooltipPrimitive.Content
    ref={ref}
    sideOffset={sideOffset}
    className={cn(
      'z-50 overflow-hidden rounded-md bg-stone-900 px-2 py-1 text-[11px] font-medium leading-tight text-stone-50 shadow-md',
      'data-[state=delayed-open]:animate-in data-[state=closed]:animate-out',
      className,
    )}
    {...props}
  />
));
TooltipContent.displayName = TooltipPrimitive.Content.displayName;

interface TooltipProps {
  content: React.ReactNode;
  children: React.ReactElement;
  side?: 'top' | 'right' | 'bottom' | 'left';
  align?: 'start' | 'center' | 'end';
  delayDuration?: number;
  /** 不渲染时直接透传 children */
  disabled?: boolean;
}

/** 便利包装组件：<Tooltip content="说明"><Button .../></Tooltip> */
export const Tooltip: React.FC<TooltipProps> = ({
  content,
  children,
  side = 'top',
  align = 'center',
  delayDuration = 250,
  disabled = false,
}) => {
  if (disabled || !content) return children;
  return (
    <TooltipRoot delayDuration={delayDuration}>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipPortal>
        <TooltipContent side={side} align={align}>
          {content}
        </TooltipContent>
      </TooltipPortal>
    </TooltipRoot>
  );
};

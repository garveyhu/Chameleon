/** Button —— waveflow 风格复刻
 *
 * 紧凑 + Inter + 蓝色 primary。
 * 7 variant × 5 size，loading 自动转圈，asChild 支持 polymorphic。
 *
 * 兼容性：保留 default 别名等于 primary，避免旧代码 import 大规模改名。
 */

import { Slot } from '@radix-ui/react-slot';
import { type VariantProps, cva } from 'class-variance-authority';
import { Loader2 } from 'lucide-react';
import * as React from 'react';

import { cn } from '@/core/lib/cn';

const buttonVariants = cva(
  'inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-md font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-200',
  {
    variants: {
      variant: {
        primary: 'bg-primary-600 text-white hover:bg-primary-700 active:bg-primary-800',
        default: 'bg-primary-600 text-white hover:bg-primary-700 active:bg-primary-800',
        outline:
          'border border-stone-300 bg-white text-stone-700 hover:bg-stone-50 active:bg-stone-100',
        secondary: 'bg-stone-100 text-stone-900 hover:bg-stone-200',
        ghost: 'text-stone-700 hover:bg-stone-100 active:bg-stone-200',
        link: 'text-primary-600 hover:underline underline-offset-2',
        danger: 'bg-red-600 text-white hover:bg-red-700 active:bg-red-800',
        'danger-outline': 'border border-red-300 text-red-600 hover:bg-red-50 active:bg-red-100',
        dark: 'bg-stone-900 text-white hover:bg-stone-800 active:bg-stone-700',
      },
      size: {
        sm: 'h-7 px-2.5 text-[11.5px]',
        md: 'h-8 px-3 text-[12.5px]',
        default: 'h-8 px-3 text-[12.5px]',
        lg: 'h-9 px-4 text-[14px]',
        icon: 'h-8 w-8 p-0',
        'icon-sm': 'h-7 w-7 p-0',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, loading, children, disabled, ...props }, ref) => {
    const styles = cn(buttonVariants({ variant, size, className }));
    // asChild 走 Radix Slot —— Slot 要求**唯一** child；在外面再插 Loader2 会让 Slot 看到
    // 两个 child（即便 loading=false 第一个是 null，React.Children.only 也会按 2 计）。
    // 业务约定：asChild 模式不支持 loading（多半用于 Link/外链，本来也不需要 loading 态）。
    if (asChild) {
      return (
        <Slot
          ref={ref as React.Ref<HTMLElement>}
          className={styles}
          {...(props as React.HTMLAttributes<HTMLElement>)}
        >
          {children}
        </Slot>
      );
    }
    return (
      <button
        ref={ref}
        className={styles}
        disabled={disabled || loading}
        {...props}
      >
        {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
        {children}
      </button>
    );
  },
);
Button.displayName = 'Button';

export { buttonVariants };

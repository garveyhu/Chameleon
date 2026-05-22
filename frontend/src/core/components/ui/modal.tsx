/** Modal —— 居中弹出表单 / 二次确认用（waveflow 风格，4 档 size） */

import * as DialogPrimitive from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import * as React from 'react';

import { cn } from '@/core/lib/cn';

export const Modal = DialogPrimitive.Root;
export const ModalTrigger = DialogPrimitive.Trigger;
export const ModalClose = DialogPrimitive.Close;
export const ModalPortal = DialogPrimitive.Portal;

const SIZE_CLASS: Record<NonNullable<ModalContentProps['size']>, string> = {
  sm: 'w-[400px]',
  md: 'w-[520px]',
  lg: 'w-[720px]',
  xl: 'w-[960px]',
};

interface ModalContentProps
  extends React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  closeOnBackdrop?: boolean;
  hideClose?: boolean;
  preventClose?: boolean;
}

export const ModalContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  ModalContentProps
>(
  (
    {
      className,
      children,
      size = 'md',
      closeOnBackdrop = true,
      hideClose = false,
      preventClose = false,
      onPointerDownOutside,
      onEscapeKeyDown,
      onInteractOutside,
      ...props
    },
    ref,
  ) => (
    <ModalPortal>
      <DialogPrimitive.Overlay
        className="modal-overlay fixed inset-0 z-50 bg-stone-950/40 backdrop-blur-sm"
      />
      <DialogPrimitive.Content
        ref={ref}
        onPointerDownOutside={e => {
          if (preventClose || !closeOnBackdrop) e.preventDefault();
          onPointerDownOutside?.(e);
        }}
        onEscapeKeyDown={e => {
          if (preventClose) e.preventDefault();
          onEscapeKeyDown?.(e);
        }}
        onInteractOutside={e => {
          if (preventClose || !closeOnBackdrop) e.preventDefault();
          onInteractOutside?.(e);
        }}
        className={cn(
          'modal-content fixed left-1/2 top-1/2 z-50 flex max-h-[90vh] flex-col overflow-hidden',
          'rounded-2xl border border-stone-200 bg-paper shadow-pop',
          SIZE_CLASS[size],
          className,
        )}
        {...props}
      >
        {children}
        {!hideClose && (
          <DialogPrimitive.Close
            className="absolute right-3.5 top-3.5 rounded-md p-1 text-stone-400 opacity-80 transition hover:bg-stone-100 hover:text-stone-700 hover:opacity-100 focus:outline-none focus:ring-1 focus:ring-blue-200"
            aria-label="关闭"
          >
            <X className="h-4 w-4" strokeWidth={1.75} />
          </DialogPrimitive.Close>
        )}
      </DialogPrimitive.Content>
    </ModalPortal>
  ),
);
ModalContent.displayName = 'ModalContent';

export const ModalHeader = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn('flex flex-col gap-1 border-b border-stone-200/70 px-5 pb-3.5 pt-4', className)}
    {...p}
  />
);

export const ModalBody = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('flex-1 overflow-y-auto px-5 py-4', className)} {...p} />
);

export const ModalFooter = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      'flex items-center justify-end gap-2 border-t border-stone-200/70 bg-warm-2/30 px-5 py-3',
      className,
    )}
    {...p}
  />
);

export const ModalTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn('text-[14px] font-semibold tracking-tight text-stone-900', className)}
    {...props}
  />
));
ModalTitle.displayName = DialogPrimitive.Title.displayName;

export const ModalDescription = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn('text-[12px] leading-relaxed text-stone-500', className)}
    {...props}
  />
));
ModalDescription.displayName = DialogPrimitive.Description.displayName;

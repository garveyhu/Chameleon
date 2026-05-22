/** Toast wrapper —— 统一封装 sonner，支持多状态 + action + promise */

import type { ExternalToast } from 'sonner';
import { toast as sonnerToast } from 'sonner';

interface ActionOption {
  label: string;
  onClick: () => void;
}

interface ToastOptions {
  description?: string;
  action?: ActionOption;
  duration?: number;
  id?: string | number;
}

const buildOpts = (opts?: ToastOptions): ExternalToast | undefined => {
  if (!opts) return undefined;
  return {
    description: opts.description,
    duration: opts.duration,
    id: opts.id,
    action: opts.action
      ? { label: opts.action.label, onClick: opts.action.onClick }
      : undefined,
  };
};

interface PromiseMessages<T> {
  loading: string;
  success: string | ((value: T) => string);
  error: string | ((err: unknown) => string);
}

export const toast = {
  success: (message: string, opts?: ToastOptions) => sonnerToast.success(message, buildOpts(opts)),
  error: (message: string, opts?: ToastOptions) => sonnerToast.error(message, buildOpts(opts)),
  warning: (message: string, opts?: ToastOptions) => sonnerToast.warning(message, buildOpts(opts)),
  info: (message: string, opts?: ToastOptions) => sonnerToast.info(message, buildOpts(opts)),
  loading: (message: string, opts?: ToastOptions) =>
    sonnerToast.loading(message, buildOpts(opts)),
  message: (message: string, opts?: ToastOptions) => sonnerToast(message, buildOpts(opts)),
  promise: <T,>(promise: Promise<T> | (() => Promise<T>), messages: PromiseMessages<T>) =>
    sonnerToast.promise(promise, messages),
  dismiss: (id?: string | number) => sonnerToast.dismiss(id),
};

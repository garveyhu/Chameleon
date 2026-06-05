/** ProviderAvatar —— 供应商品牌化单字图标。
 *
 * 替代千篇一律的灰云图标：按 provider code 给出品牌色 + 短标，提升可扫性。
 * 未知 code 回退到首两字母 + 中性色。孤儿（__deleted_*）回退处理由调用方决定。
 */

import { cn } from '@/core/lib/cn';

interface Brand {
  label: string;
  cls: string;
}

const BRAND: Record<string, Brand> = {
  deepseek: { label: 'DS', cls: 'bg-blue-50 text-blue-600 ring-blue-100' },
  qwen: { label: '通', cls: 'bg-violet-50 text-violet-600 ring-violet-100' },
  openai: { label: 'AI', cls: 'bg-emerald-50 text-emerald-600 ring-emerald-100' },
  'new-api': { label: '⇄', cls: 'bg-primary-50 text-primary-600 ring-primary-100' },
  oneapi: { label: '⇄', cls: 'bg-primary-50 text-primary-600 ring-primary-100' },
  dify: { label: 'Di', cls: 'bg-indigo-50 text-indigo-600 ring-indigo-100' },
  fastgpt: { label: 'FG', cls: 'bg-cyan-50 text-cyan-600 ring-cyan-100' },
  coze: { label: 'Cz', cls: 'bg-amber-50 text-amber-600 ring-amber-100' },
};

const FALLBACK: Brand = { label: '?', cls: 'bg-stone-100 text-stone-500 ring-stone-200' };

const SIZE = {
  sm: 'h-8 w-8 text-[11px]',
  md: 'h-10 w-10 text-[13px]',
} as const;

interface Props {
  code: string | null | undefined;
  size?: keyof typeof SIZE;
  className?: string;
}

export const ProviderAvatar = ({ code, size = 'sm', className }: Props) => {
  const key = (code || '').toLowerCase().replace(/__deleted.*/, '');
  const brand: Brand =
    BRAND[key] ??
    (key
      ? { label: key.slice(0, 2).toUpperCase(), cls: FALLBACK.cls }
      : FALLBACK);
  return (
    <div
      className={cn(
        'flex shrink-0 items-center justify-center rounded-lg font-semibold ring-1 ring-inset',
        SIZE[size],
        brand.cls,
        className,
      )}
    >
      {brand.label}
    </div>
  );
};

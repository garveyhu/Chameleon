/** SectionCard —— 业务页统一卡片容器（复刻 waveflow）
 *
 * 样式：rounded-xl + border-stone-200/40 + bg-paper + p-5 + shadow-soft
 * 内含 TableToolbar + DataTable + TablePagination
 */

import type { ReactNode } from 'react';

import { cn } from '@/core/lib/cn';

interface SectionCardProps {
  children: ReactNode;
  className?: string;
}

export const SectionCard = ({ children, className }: SectionCardProps) => (
  <section
    className={cn(
      'rounded-xl border border-stone-200/40 bg-[var(--color-paper)] p-5 shadow-[var(--shadow-soft)]',
      className,
    )}
  >
    {children}
  </section>
);

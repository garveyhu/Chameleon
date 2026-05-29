/** StatBar —— 指标平铺横条（trace 详情 / 会话详情共用）
 *
 * 视觉：无填充无卡格；指标间极淡竖发丝分隔；label 小灰 + value 放大加粗出层次。
 * 单一职责：只排版指标，数值/语义由调用方算好传入。
 */

import type { ReactNode } from 'react';

import { cn } from '@/core/lib/cn';

export const StatBar = ({ children }: { children: ReactNode }) => (
  <div className="flex flex-wrap gap-y-3 py-1">{children}</div>
);

/** 单项指标：label 小灰 + value 粗，右侧竖发丝线分隔 */
export const StatItem = ({
  k,
  v,
  sub,
  mono,
  tone,
}: {
  k: string;
  v: ReactNode;
  sub?: ReactNode;
  mono?: boolean;
  tone?: 'ok' | 'err';
}) => (
  <div className="mr-4 border-r border-stone-100 pr-4 last:mr-0 last:border-r-0 last:pr-0">
    <div className="text-[10.5px] tracking-wide text-stone-400">{k}</div>
    <div className="mt-1 flex items-baseline gap-1.5">
      <span
        className={cn(
          'tnum text-[15px] font-semibold',
          tone === 'ok' ? 'text-emerald-600' : tone === 'err' ? 'text-rose-600' : 'text-stone-800',
          mono && 'font-mono text-[13px]',
        )}
      >
        {v}
      </span>
      {sub && <span className="tnum text-[11px] font-normal text-stone-400">{sub}</span>}
    </div>
  </div>
);

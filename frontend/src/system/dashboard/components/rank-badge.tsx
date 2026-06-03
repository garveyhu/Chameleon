/** 排名徽章 —— 前三名金/银/铜，其余灰。用于 Top / 维度排行表的名称列。 */
import { cn } from '@/core/lib/cn';

const TONE = [
  'bg-amber-100 text-amber-700 ring-amber-200',
  'bg-slate-200 text-slate-600 ring-slate-300',
  'bg-orange-100 text-orange-700 ring-orange-200',
];

export const RankBadge = ({ index }: { index: number }) => (
  <span
    className={cn(
      'inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold tabular-nums ring-1 ring-inset',
      TONE[index] ?? 'bg-stone-100 text-stone-400 ring-stone-200',
    )}
  >
    {index + 1}
  </span>
);

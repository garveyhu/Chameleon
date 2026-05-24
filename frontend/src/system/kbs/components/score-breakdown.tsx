/** 命中得分分项条形图：综合 + vector / bm25 / rerank（B6 接入后显示分项）
 *
 * 仅渲染存在的分项（后端未启用对应通道时缺省）。分值按 0–1 归一展示。
 */

import { cn } from '@/core/lib/cn';
import type { SearchHitItem } from '@/system/kbs/types/kb';

interface Dimension {
  key: keyof Pick<
    SearchHitItem,
    'vector_score' | 'bm25_score' | 'rerank_score'
  >;
  label: string;
  bar: string;
}

const DIMENSIONS: Dimension[] = [
  { key: 'vector_score', label: '向量', bar: 'bg-sky-500' },
  { key: 'bm25_score', label: 'BM25', bar: 'bg-amber-500' },
  { key: 'rerank_score', label: 'rerank', bar: 'bg-violet-500' },
];

const pct = (v: number) => Math.max(0, Math.min(100, Math.round(v * 100)));

interface Props {
  hit: SearchHitItem;
  /** 紧凑模式：只渲染综合得分一条（用于列表卡片） */
  compact?: boolean;
}

export const ScoreBreakdown = ({ hit, compact }: Props) => {
  const dims = DIMENSIONS.filter(d => hit[d.key] != null);

  return (
    <div className="space-y-1">
      <ScoreRow label="综合" value={hit.score} bar="bg-emerald-500" strong />
      {!compact &&
        dims.map(d => (
          <ScoreRow
            key={d.key}
            label={d.label}
            value={hit[d.key] as number}
            bar={d.bar}
          />
        ))}
    </div>
  );
};

const ScoreRow = ({
  label,
  value,
  bar,
  strong,
}: {
  label: string;
  value: number;
  bar: string;
  strong?: boolean;
}) => (
  <div className="flex items-center gap-2">
    <span
      className={cn(
        'w-12 shrink-0 text-right text-[10.5px]',
        strong ? 'font-medium text-stone-700' : 'text-stone-500',
      )}
    >
      {label}
    </span>
    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-stone-100">
      <div
        className={cn('h-full rounded-full', bar)}
        style={{ width: `${pct(value)}%` }}
      />
    </div>
    <span className="w-9 shrink-0 text-right font-mono text-[10.5px] tabular-nums text-stone-600">
      {pct(value)}%
    </span>
  </div>
);

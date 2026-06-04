/** 评分明细渲染（复用） —— 逐项原始分：raw_1_5 星级 / GSB verdict 徽章 / 其它数值。
 *  供样本详情侧栏 + 对比页复用。 */

import { Star } from 'lucide-react';

import { Badge } from '@/core/components/ui/badge';
import { cn } from '@/core/lib/cn';
import { formatScore } from '@/core/lib/score';
import { verdictOf } from '@/system/datasets/utils/verdict';

interface FieldScoresProps {
  fieldScores: Record<string, number | string | null> | null | undefined;
  score: number | null;
}

/** raw_1_5 星级 / verdict 徽章 / 其它数值 label:value；无 field_scores 整块不渲染。 */
export const FieldScores = ({ fieldScores, score }: FieldScoresProps) => {
  if (!fieldScores || Object.keys(fieldScores).length === 0) return null;

  const raw = fieldScores.raw_1_5;
  const verdict = verdictOf(fieldScores);
  const rest = Object.entries(fieldScores).filter(
    ([k]) => k !== 'raw_1_5' && k !== 'verdict',
  );

  return (
    <div>
      <div className="mb-1 text-[10.5px] text-stone-500">评分明细</div>
      <div className="flex flex-wrap items-center gap-3 rounded border border-stone-200 bg-white px-2.5 py-2">
        {typeof raw === 'number' && (
          <div className="flex items-center gap-1.5">
            <StarRating value={raw} />
            <span className="text-[11px] text-stone-600">
              {raw}/5
              {score != null && (
                <span className="text-stone-400"> · 归一 {formatScore(score)}</span>
              )}
            </span>
          </div>
        )}
        {verdict && (
          <div className="flex items-center gap-1.5">
            <Badge variant={verdict.variant} className="text-[10.5px]">
              {verdict.label}（{String(fieldScores.verdict)}）
            </Badge>
            <span className="text-[10.5px] text-stone-400">GSB 判定</span>
          </div>
        )}
        {rest.map(([k, v]) => (
          <div key={k} className="text-[11px] text-stone-600">
            <span className="text-stone-400">{k}：</span>
            {v == null ? '—' : String(v)}
          </div>
        ))}
      </div>
    </div>
  );
};

/** 1–5 档星级（整数填充，空星灰显） */
export const StarRating = ({ value }: { value: number }) => {
  const filled = Math.max(0, Math.min(5, Math.round(value)));
  return (
    <span className="inline-flex items-center gap-0.5" aria-label={`${value}/5`}>
      {Array.from({ length: 5 }, (_, i) => (
        <Star
          key={i}
          className={cn(
            'h-3.5 w-3.5',
            i < filled
              ? 'fill-amber-400 text-amber-400'
              : 'fill-stone-200 text-stone-200',
          )}
        />
      ))}
    </span>
  );
};

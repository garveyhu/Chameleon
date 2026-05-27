/** 命中得分展示：相关度档位 + 各通道相似度分项（向量 / 关键词 / 精排）
 *
 * 设计取舍：
 * - 「综合」融合分在混合模式是 RRF 很小的绝对值，直接显示百分比看不懂 → 不展示原始融合分，
 *   改用「本次结果集内相对最高分」归一出的 最相关/相关/弱相关 档位做快速判断。
 * - 但各通道分项（向量余弦 0–1 / 关键词 BM25 归一 / 精排分）是有意义的相似度，必须显示出来：
 *   它们就是用户要看的「相似度 / 相似比例」，也是判断关键词召回是否命中的依据。
 */

import { cn } from '@/core/lib/cn';
import type { SearchHitItem } from '@/system/kbs/types/kb';

interface Channel {
  key: keyof Pick<SearchHitItem, 'vector_score' | 'bm25_score' | 'rerank_score'>;
  label: string;
  short: string;
  bar: string;
}

const CHANNELS: Channel[] = [
  { key: 'vector_score', label: '向量相似度', short: '向量', bar: 'bg-sky-500' },
  { key: 'bm25_score', label: '关键词匹配', short: '关键词', bar: 'bg-amber-500' },
  { key: 'rerank_score', label: '精排得分', short: '精排', bar: 'bg-violet-500' },
];

const clampPct = (v: number) => Math.max(0, Math.min(100, Math.round(v * 100)));

function relevance(score: number, maxScore: number) {
  const ratio = maxScore > 0 ? score / maxScore : 0;
  if (ratio >= 0.85) return { label: '最相关', cls: 'bg-emerald-50 text-emerald-700' };
  if (ratio >= 0.55) return { label: '相关', cls: 'bg-amber-50 text-amber-700' };
  return { label: '弱相关', cls: 'bg-stone-100 text-stone-500' };
}

interface Props {
  hit: SearchHitItem;
  /** 本次结果集内的最高综合分，用于归一出相对相关度档位 */
  maxScore: number;
  /** 紧凑模式：列表卡片用 —— 档位 + 一行通道分数 */
  compact?: boolean;
}

export const ScoreBreakdown = ({ hit, maxScore, compact }: Props) => {
  const r = relevance(hit.score, maxScore);
  const channels = CHANNELS.filter(c => hit[c.key] != null);

  if (compact) {
    return (
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
        <span className={cn('shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium', r.cls)}>
          {r.label}
        </span>
        {channels.map(c => (
          <span key={c.key} className="text-[10.5px] text-stone-500">
            {c.short}
            <span className="ml-0.5 font-mono tabular-nums text-stone-700">
              {clampPct(hit[c.key] as number)}%
            </span>
          </span>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <span className={cn('shrink-0 rounded px-2 py-0.5 text-[11.5px] font-medium', r.cls)}>
          {r.label}
        </span>
        <span className="text-[10.5px] text-stone-400">本次结果中的相对相关度</span>
      </div>
      {channels.length > 0 ? (
        <div className="space-y-1">
          {channels.map(c => (
            <ChannelRow
              key={c.key}
              label={c.label}
              value={hit[c.key] as number}
              bar={c.bar}
            />
          ))}
        </div>
      ) : (
        <div className="text-[10.5px] text-stone-400">该召回模式无分项（仅综合排序）</div>
      )}
    </div>
  );
};

const ChannelRow = ({ label, value, bar }: { label: string; value: number; bar: string }) => (
  <div className="flex items-center gap-2">
    <span className="w-16 shrink-0 text-right text-[10.5px] text-stone-500">{label}</span>
    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-stone-100">
      <div className={cn('h-full rounded-full', bar)} style={{ width: `${clampPct(value)}%` }} />
    </div>
    <span className="w-9 shrink-0 text-right font-mono text-[10.5px] tabular-nums text-stone-600">
      {clampPct(value)}%
    </span>
  </div>
);

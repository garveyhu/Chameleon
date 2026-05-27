/** 命中得分展示：各通道相似度分项（向量 / 关键词 / 精排）
 *
 * 不展示融合「综合」分：混合模式融合走 RRF，各命中的融合分量纲很小且彼此极接近，
 * 无论显示百分比还是归一成档位都没有区分度（会全部落进「最相关」）。各通道原始分
 * （向量余弦 0–1 / 关键词 BM25 归一 / 精排分）才是有意义、有高低差异的相似度，直接显示。
 * 结果已按融合分排序（#1 最靠前），排名即综合相关度的体现。
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

interface Props {
  hit: SearchHitItem;
  /** 紧凑模式：列表卡片用 —— 一行通道分数 */
  compact?: boolean;
}

export const ScoreBreakdown = ({ hit, compact }: Props) => {
  const channels = CHANNELS.filter(c => hit[c.key] != null);

  if (channels.length === 0) {
    return compact ? null : (
      <div className="text-[10.5px] text-stone-400">仅按综合排序，无分项</div>
    );
  }

  if (compact) {
    return (
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5">
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
    <div className="space-y-1">
      {channels.map(c => (
        <ChannelRow key={c.key} label={c.label} value={hit[c.key] as number} bar={c.bar} />
      ))}
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

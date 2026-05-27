/** 命中相关度展示：相对相关度（同次结果内归一）+ 可选匹配明细
 *
 * 不同召回模式的分值量纲不同（向量是 0–1 余弦；混合 RRF 是很小的绝对值），
 * 直接显示百分比会让用户看不懂（混合模式下「综合」可能只有个位数 %）。
 * 这里改用「本次结果集内相对最高分」的相对相关度 + 高/中/低 文字档位，
 * 与召回模式无关、普通用户也能看懂。原始分通道分项收进可展开的「匹配明细」。
 */

import { cn } from '@/core/lib/cn';
import type { SearchHitItem } from '@/system/kbs/types/kb';

interface Channel {
  key: keyof Pick<SearchHitItem, 'vector_score' | 'bm25_score' | 'rerank_score'>;
  label: string;
  bar: string;
}

const CHANNELS: Channel[] = [
  { key: 'vector_score', label: '语义匹配', bar: 'bg-sky-500' },
  { key: 'bm25_score', label: '关键词匹配', bar: 'bg-amber-500' },
  { key: 'rerank_score', label: '精排重排', bar: 'bg-violet-500' },
];

const clampPct = (v: number) => Math.max(0, Math.min(100, Math.round(v * 100)));

function relevance(score: number, maxScore: number) {
  const ratio = maxScore > 0 ? score / maxScore : 0;
  if (ratio >= 0.85) return { pct: clampPct(ratio), label: '最相关', cls: 'bg-emerald-50 text-emerald-700' };
  if (ratio >= 0.55) return { pct: clampPct(ratio), label: '相关', cls: 'bg-amber-50 text-amber-700' };
  return { pct: clampPct(ratio), label: '弱相关', cls: 'bg-stone-100 text-stone-500' };
}

interface Props {
  hit: SearchHitItem;
  /** 本次结果集内的最高综合分，用于归一出相对相关度 */
  maxScore: number;
  /** 紧凑模式：列表卡片用，只显示相关度档位 + 细条 */
  compact?: boolean;
}

export const ScoreBreakdown = ({ hit, maxScore, compact }: Props) => {
  const r = relevance(hit.score, maxScore);
  const channels = CHANNELS.filter(c => hit[c.key] != null);

  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <span className={cn('shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium', r.cls)}>
          {r.label}
        </span>
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-stone-100">
          <div className="h-full rounded-full bg-emerald-500" style={{ width: `${r.pct}%` }} />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <span className={cn('shrink-0 rounded px-2 py-0.5 text-[11.5px] font-medium', r.cls)}>
          {r.label}
        </span>
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-stone-100">
          <div className="h-full rounded-full bg-emerald-500" style={{ width: `${r.pct}%` }} />
        </div>
      </div>
      {channels.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer list-none text-[10.5px] text-stone-400 hover:text-stone-600">
            匹配明细（调参参考）▾
          </summary>
          <div className="mt-1 space-y-1">
            {channels.map(c => (
              <ChannelRow key={c.key} label={c.label} value={hit[c.key] as number} bar={c.bar} />
            ))}
          </div>
        </details>
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
    <span className="w-9 shrink-0 text-right font-mono text-[10.5px] tabular-nums text-stone-400">
      {clampPct(value)}%
    </span>
  </div>
);

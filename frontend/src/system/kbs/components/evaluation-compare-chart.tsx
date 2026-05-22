/** 评估批次对比折线图（hit@5 / MRR 趋势）—— 不引图表库，纯 SVG */

import type { EvaluationListItem } from '@/system/kbs/types/evaluation';

interface Props {
  evals: EvaluationListItem[];
}

const W = 720;
const H = 200;
const PAD = { top: 16, right: 16, bottom: 28, left: 36 };

export const EvaluationCompareChart = ({ evals }: Props) => {
  // 仅画 done 且有指标的批次
  const points = evals
    .filter(e => e.status === 'done' && e.hit_at_5 != null && e.mrr != null)
    .slice()
    .reverse(); // 按时间正序

  if (points.length < 2) {
    return (
      <div className="flex h-[200px] items-center justify-center text-[12px] text-stone-400">
        至少要 2 个已完成评估才能对比趋势
      </div>
    );
  }

  const xs = points.map((_, i) => i);
  const w = W - PAD.left - PAD.right;
  const h = H - PAD.top - PAD.bottom;
  const xStep = points.length > 1 ? w / (points.length - 1) : 0;

  const linePath = (vals: number[]) =>
    vals
      .map((v, i) => {
        const x = PAD.left + xs[i] * xStep;
        const y = PAD.top + (1 - v) * h;
        return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');

  const hit5 = points.map(p => p.hit_at_5 ?? 0);
  const mrr = points.map(p => p.mrr ?? 0);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {/* y 轴刻度 0 / 0.5 / 1 */}
      {[0, 0.5, 1].map(t => {
        const y = PAD.top + (1 - t) * h;
        return (
          <g key={t}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y}
              y2={y}
              stroke="#e7e5e4"
              strokeDasharray="2 4"
            />
            <text
              x={PAD.left - 6}
              y={y + 3}
              textAnchor="end"
              className="fill-stone-500"
              style={{ fontSize: 10 }}
            >
              {t.toFixed(1)}
            </text>
          </g>
        );
      })}
      {/* x 轴标签 */}
      {points.map((p, i) => (
        <text
          key={p.id}
          x={PAD.left + xs[i] * xStep}
          y={H - PAD.bottom + 14}
          textAnchor="middle"
          className="fill-stone-500"
          style={{ fontSize: 10 }}
        >
          {p.name.slice(0, 12)}
        </text>
      ))}
      {/* hit@5 折线 */}
      <path
        d={linePath(hit5)}
        fill="none"
        stroke="#d97706"
        strokeWidth={1.6}
      />
      {hit5.map((v, i) => (
        <circle
          key={`h-${i}`}
          cx={PAD.left + xs[i] * xStep}
          cy={PAD.top + (1 - v) * h}
          r={3}
          fill="#d97706"
        />
      ))}
      {/* MRR 折线 */}
      <path
        d={linePath(mrr)}
        fill="none"
        stroke="#0284c7"
        strokeWidth={1.6}
      />
      {mrr.map((v, i) => (
        <circle
          key={`m-${i}`}
          cx={PAD.left + xs[i] * xStep}
          cy={PAD.top + (1 - v) * h}
          r={3}
          fill="#0284c7"
        />
      ))}
      {/* 图例 */}
      <g transform={`translate(${PAD.left}, ${PAD.top - 4})`}>
        <circle cx={4} cy={4} r={3} fill="#d97706" />
        <text x={10} y={7} className="fill-stone-700" style={{ fontSize: 10 }}>
          hit@5
        </text>
        <circle cx={60} cy={4} r={3} fill="#0284c7" />
        <text x={66} y={7} className="fill-stone-700" style={{ fontSize: 10 }}>
          MRR
        </text>
      </g>
    </svg>
  );
};

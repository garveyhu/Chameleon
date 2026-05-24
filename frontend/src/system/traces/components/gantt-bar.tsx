/** Gantt 单行的时间条：按几何定位的 bar + 时长文字 + 叠加 cost-label */

import { cn } from '@/core/lib/cn';
import { formatDurationMs } from '@/core/lib/format';
import { CostLabel } from '@/system/traces/components/cost-label';
import type {
  ObservationType,
  TraceTreeNode,
} from '@/system/call_logs/types/call-log';
import { barGeometry, type TimeBounds } from '@/system/traces/utils/gantt-model';

/** 按 observation_type 着色（失败统一玫瑰色） */
const OBS_COLOR: Record<ObservationType, string> = {
  trace: 'bg-stone-400',
  span: 'bg-sky-400',
  generation: 'bg-violet-400',
  agent: 'bg-indigo-400',
  tool: 'bg-amber-400',
  retriever: 'bg-teal-400',
  evaluator: 'bg-fuchsia-400',
  embedding: 'bg-cyan-400',
  guardrail: 'bg-rose-300',
};

interface Props {
  node: TraceTreeNode;
  bounds: TimeBounds;
  selected: boolean;
  hovered: boolean;
}

export const GanttBar = ({ node, bounds, selected, hovered }: Props) => {
  const { leftPct, widthPct } = barGeometry(node, bounds);
  const color = node.success
    ? (OBS_COLOR[node.observation_type] ?? 'bg-stone-400')
    : 'bg-rose-500';
  // cost-label 默认贴在 bar 右侧；bar 太靠右时改贴左侧避免溢出
  const labelOnRight = leftPct + widthPct < 82;

  return (
    <div className="relative h-full w-full">
      <div
        className={cn(
          'absolute top-1/2 h-[14px] -translate-y-1/2 rounded-[3px] transition',
          color,
          selected && 'ring-2 ring-stone-800 ring-offset-1',
          hovered && !selected && 'brightness-110 ring-1 ring-stone-500',
        )}
        style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
        title={`${node.agent_key} · ${formatDurationMs(node.duration_ms)}`}
      >
        {widthPct > 12 && (
          <span className="pointer-events-none flex h-full items-center justify-center px-1 font-mono text-[9.5px] text-white/90">
            {formatDurationMs(node.duration_ms)}
          </span>
        )}
      </div>
      <span
        className="absolute top-1/2 -translate-y-1/2 whitespace-nowrap px-1.5"
        style={
          labelOnRight
            ? { left: `${leftPct + widthPct}%` }
            : { right: `${100 - leftPct}%` }
        }
      >
        <CostLabel node={node} />
      </span>
    </div>
  );
};

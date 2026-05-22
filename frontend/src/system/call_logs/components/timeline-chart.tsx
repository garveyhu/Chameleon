/** Timeline 横条 —— 5 段 span 拼接 + 比例宽度 + hover tooltip */

import { cn } from '@/core/lib/cn';
import { Tooltip } from '@/core/components/ui/tooltip';
import type { SpanRecord } from '@/system/call_logs/types/call-log';

interface Props {
  spans: SpanRecord[];
  totalMs: number;
}

const COLOR: Record<string, string> = {
  agent_resolve: 'bg-sky-500',
  conversation_setup: 'bg-indigo-500',
  history_persist: 'bg-violet-500',
  prepare_invocation: 'bg-indigo-500',
  provider_invoke: 'bg-amber-500',
  response_persist: 'bg-emerald-500',
};

const FALLBACK = 'bg-stone-400';

export const TimelineChart = ({ spans, totalMs }: Props) => {
  if (!spans || spans.length === 0 || totalMs <= 0) {
    return (
      <div className="rounded-md border border-dashed border-stone-300 py-6 text-center text-[12px] text-stone-400">
        无 spans 数据
      </div>
    );
  }

  // 总轴长 = max(end_ms) 与 totalMs 中较大的（避免 spans 漂出 duration）
  const axisMax = Math.max(
    totalMs,
    ...spans.map(s => s.end_ms),
    ...spans.map(s => s.start_ms),
  );

  return (
    <div className="space-y-2">
      {/* 横条轴 */}
      <div className="relative h-6 overflow-hidden rounded-md bg-stone-100">
        {spans.map((s, i) => {
          const left = (s.start_ms / axisMax) * 100;
          const width = ((s.end_ms - s.start_ms) / axisMax) * 100;
          const cls = COLOR[s.name] ?? FALLBACK;
          return (
            <Tooltip
              key={`${s.name}-${i}`}
              content={
                <div className="space-y-0.5">
                  <div>
                    <strong>{s.name}</strong>
                  </div>
                  <div>
                    {(s.end_ms - s.start_ms).toFixed(1)} ms (
                    {s.start_ms.toFixed(0)}→{s.end_ms.toFixed(0)})
                  </div>
                  <div>status: {s.status}</div>
                  {s.error_message && (
                    <div className="text-rose-300">{s.error_message}</div>
                  )}
                </div>
              }
            >
              <div
                className={cn(
                  'absolute top-0 h-full transition-opacity hover:opacity-90',
                  cls,
                  s.status === 'failed' && 'ring-1 ring-rose-300',
                )}
                style={{
                  left: `${left}%`,
                  width: `${Math.max(width, 0.5)}%`,
                }}
              />
            </Tooltip>
          );
        })}
      </div>
      {/* 列表 */}
      <ul className="space-y-1 text-[11.5px]">
        {spans.map((s, i) => {
          const dur = s.end_ms - s.start_ms;
          const cls = COLOR[s.name] ?? FALLBACK;
          return (
            <li
              key={`${s.name}-li-${i}`}
              className={cn(
                'flex items-center gap-2 rounded-md px-2 py-1',
                s.status === 'failed' ? 'bg-rose-50' : 'bg-stone-50',
              )}
            >
              <span className={cn('inline-block h-2 w-2 shrink-0 rounded-sm', cls)} />
              <span className="min-w-[140px] font-mono text-stone-700">
                {s.name}
              </span>
              <span className="font-mono tnum text-stone-500">
                {dur.toFixed(1)}ms
              </span>
              <span className="ml-auto font-mono tnum text-stone-400">
                {s.start_ms.toFixed(0)}→{s.end_ms.toFixed(0)}
              </span>
              {s.status === 'failed' && (
                <span className="text-[10.5px] text-rose-600">{s.error_message}</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
};

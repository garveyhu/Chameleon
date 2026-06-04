/** 运行详情整页左窄栏（master） —— 本 dataset 的 run 列表，点切换、当前高亮。 */

import { Sparkles } from 'lucide-react';

import { Badge } from '@/core/components/ui/badge';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import { formatScore, scoreColor } from '@/core/lib/score';
import type { EntityId } from '@/core/types/api';
import type { DatasetRunRow } from '@/system/datasets/types/dataset';

const STATUS_LABEL: Record<string, string> = {
  pending: '等待',
  running: '运行中',
  success: '成功',
  failed: '失败',
  cancelled: '已取消',
};
const statusDot = (s: string): string =>
  s === 'success' ? 'bg-emerald-400' : s === 'failed' ? 'bg-rose-400' : 'bg-stone-300';

const runScore = (r: DatasetRunRow): number | null => {
  const s = r.summary as Record<string, unknown> | null;
  const v = s?.mean_score ?? s?.mean ?? s?.avg_score;
  return typeof v === 'number' ? v : null;
};

interface Props {
  runs: DatasetRunRow[];
  activeRunId: EntityId;
  loading?: boolean;
  onSelect: (runId: EntityId) => void;
}

export const RunListRail = ({ runs, activeRunId, loading, onSelect }: Props) => (
  <aside className="flex h-full w-[244px] shrink-0 flex-col overflow-hidden border-r border-stone-200 bg-white">
    <div className="border-b border-stone-200 px-3 py-2.5 text-[12px] font-medium text-stone-700">
      运行（{runs.length}）
    </div>
    <div className="flex-1 overflow-auto py-1">
      {loading && runs.length === 0 ? (
        <div className="px-3 py-4 text-[11.5px] text-stone-400">加载中…</div>
      ) : runs.length === 0 ? (
        <div className="px-3 py-4 text-[11.5px] text-stone-400">暂无运行</div>
      ) : (
        runs.map(r => {
          const active = String(r.id) === String(activeRunId);
          const score = runScore(r);
          return (
            <button
              key={String(r.id)}
              type="button"
              onClick={() => onSelect(r.id)}
              className={cn(
                'flex w-full flex-col gap-1 border-l-2 px-3 py-2 text-left transition',
                active
                  ? 'border-stone-800 bg-stone-50'
                  : 'border-transparent hover:bg-stone-50/60',
              )}
            >
              <div className="flex items-center gap-1.5">
                <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', statusDot(r.status))} />
                <span
                  className={cn(
                    'flex-1 truncate text-[12.5px]',
                    active ? 'font-medium text-stone-900' : 'text-stone-700',
                  )}
                  title={r.name}
                >
                  {r.name}
                </span>
                {r.has_optimization && (
                  <span title="已生成优化 Prompt">
                    <Sparkles className="h-3 w-3 text-violet-400" />
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1.5 pl-3">
                {r.parent_run_id != null && (
                  <Badge
                    variant="outline"
                    className="bg-violet-50 px-1 py-0 text-[9px] text-violet-700"
                  >
                    优化产物
                  </Badge>
                )}
                <span className={cn('tnum text-[11px]', scoreColor(score))}>
                  {score != null ? formatScore(score) : '—'}
                </span>
                <span className="ml-auto text-[10px] text-stone-400">
                  {STATUS_LABEL[r.status] ?? r.status}
                </span>
              </div>
              <div className="pl-3 text-[9.5px] text-stone-400">
                {formatDateTime(r.created_at)}
              </div>
            </button>
          );
        })
      )}
    </div>
  </aside>
);

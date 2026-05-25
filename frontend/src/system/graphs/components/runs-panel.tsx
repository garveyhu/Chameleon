/** 编辑器右上 History 按钮打开的 runs 列表（替代 NodeInspector）
 *
 * 点击一行跳到 /call-logs?app_id=system 用 trace tree drawer 看嵌套结构。
 */
import { useNavigate } from 'react-router-dom';

import { X } from 'lucide-react';

import { Badge } from '@/core/components/ui/badge';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import type { GraphRunItem } from '@/system/graphs/types/graph';

interface Props {
  runs: GraphRunItem[];
  loading: boolean;
  onClose: () => void;
}

export const RunsPanel = ({ runs, loading, onClose }: Props) => {
  const nav = useNavigate();
  return (
    <aside className="bg-warm-2/40 flex h-full w-full flex-col gap-1 overflow-y-auto p-3">
      <header className="mb-1 flex items-center justify-between">
        <div>
          <div className="text-[10.5px] tracking-wider text-stone-500 uppercase">历史 runs</div>
          <div className="text-[11px] text-stone-700">{runs.length} 条</div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-stone-400 hover:bg-stone-100 hover:text-stone-700"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </header>

      {loading ? (
        <div className="py-6 text-center text-[11px] text-stone-400">加载中…</div>
      ) : runs.length === 0 ? (
        <div className="py-6 text-center text-[11px] text-stone-400">
          还没有运行记录；点上方 "Run" 持久化跑一次
        </div>
      ) : (
        runs.map(r => (
          <button
            key={String(r.id)}
            type="button"
            onClick={() => nav(`/call-logs?app_id=system`)}
            className={cn(
              'rounded-md border border-stone-200 bg-white px-2 py-1.5 text-left text-[11.5px]',
              'transition hover:border-stone-300 hover:bg-stone-50',
            )}
            title="跳到调用日志页 · trace tree drawer 看嵌套结构"
          >
            <div className="flex items-center justify-between">
              <Badge
                variant="outline"
                className={cn(
                  'text-[10px]',
                  r.status === 'success'
                    ? 'bg-emerald-50 text-emerald-700'
                    : r.status === 'failed'
                      ? 'bg-rose-50 text-rose-700'
                      : 'bg-stone-50 text-stone-600',
                )}
              >
                {r.status}
              </Badge>
              <span className="tnum font-mono text-[10.5px] text-stone-500">
                {r.duration_ms ?? '—'}ms · {r.node_count ?? '—'} 节点
              </span>
            </div>
            <div className="mt-1 truncate font-mono text-[10px] text-stone-500">{r.request_id}</div>
            <div className="text-[10px] text-stone-400">{formatDateTime(r.created_at)}</div>
          </button>
        ))
      )}
    </aside>
  );
};

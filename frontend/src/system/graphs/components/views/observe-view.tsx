/** 监测视图 —— 两个子 tab：日志（运行历史）/ 监测（运行指标）
 *
 * 把原先分列在二级导航的「日志」「监测」收进一个视图，用顶部 tab 切换。
 */
import { useState } from 'react';

import { Activity, ScrollText } from 'lucide-react';

import { cn } from '@/core/lib/cn';
import type { EntityId } from '@/core/types/api';
import { LogsView } from '@/system/graphs/components/views/logs-view';
import { MonitorView } from '@/system/graphs/components/views/monitor-view';

type SubTab = 'logs' | 'metrics';

interface Props {
  graphId: EntityId;
  graphName: string;
  openRunId: EntityId | null;
  onOpenRun: (id: EntityId | null) => void;
}

const SUB_TABS: { key: SubTab; label: string; icon: typeof ScrollText }[] = [
  { key: 'logs', label: '日志', icon: ScrollText },
  { key: 'metrics', label: '监测', icon: Activity },
];

export const ObserveView = ({ graphId, graphName, openRunId, onOpenRun }: Props) => {
  const [sub, setSub] = useState<SubTab>('logs');

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-1 border-b border-stone-200/70 px-4 py-2">
        {SUB_TABS.map(t => (
          <button
            key={t.key}
            type="button"
            onClick={() => setSub(t.key)}
            className={cn(
              'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12.5px] font-medium transition',
              sub === t.key
                ? 'bg-blue-50 text-blue-700'
                : 'text-stone-500 hover:bg-stone-100 hover:text-stone-700',
            )}
          >
            <t.icon className={cn('h-3.5 w-3.5', sub === t.key ? 'text-blue-600' : 'text-stone-400')} />
            {t.label}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {sub === 'logs' ? (
          <LogsView
            graphId={graphId}
            graphName={graphName}
            openRunId={openRunId}
            onOpenRun={onOpenRun}
          />
        ) : (
          <MonitorView graphId={graphId} />
        )}
      </div>
    </div>
  );
};

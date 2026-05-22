/** TraceDrawer —— call_log 行点击展开的 5-tab Sheet */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { JsonViewer } from '@/core/components/common/json-viewer';
import { Badge } from '@/core/components/ui/badge';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import { ObservationTree } from '@/system/call_logs/components/observation-tree';
import { TimelineChart } from '@/system/call_logs/components/timeline-chart';
import { callLogApi } from '@/system/call_logs/services/call-log';
import type { CallLogItem } from '@/system/call_logs/types/call-log';

type TabKey = 'tree' | 'request' | 'response' | 'timeline' | 'logs' | 'raw';

interface TabDef {
  key: TabKey;
  label: string;
}

const TABS: TabDef[] = [
  { key: 'tree', label: 'Tree' },
  { key: 'request', label: 'Request' },
  { key: 'response', label: 'Response' },
  { key: 'timeline', label: 'Timeline' },
  { key: 'logs', label: 'Logs' },
  { key: 'raw', label: 'Raw' },
];

interface Props {
  callLog: CallLogItem | null;
  onClose: () => void;
}

export const TraceDrawer = ({ callLog, onClose }: Props) => {
  const [tab, setTab] = useState<TabKey>('tree');

  const detailQ = useQuery({
    queryKey: ['call-log-detail', callLog?.id],
    queryFn: () => callLogApi.get(callLog!.id),
    enabled: callLog != null,
  });

  // 仅当 Tree tab 激活时拉嵌套树（用 request_id 而非 id）
  const treeQ = useQuery({
    queryKey: ['call-log-tree', callLog?.request_id],
    queryFn: () => callLogApi.tree(callLog!.request_id),
    enabled: callLog != null && tab === 'tree',
  });

  return (
    <Sheet
      open={callLog != null}
      onOpenChange={o => !o && onClose()}
    >
      <SheetContent width="w-[820px]">
        <SheetHeader>
          <SheetTitle>
            {callLog ? (
              <div className="flex items-center gap-2">
                <span>{callLog.agent_key}</span>
                <span className="font-mono text-[11.5px] text-stone-500">
                  req_id={callLog.request_id.slice(0, 16)}…
                </span>
                <Badge
                  variant="outline"
                  className={cn(
                    'text-[10.5px]',
                    callLog.success
                      ? 'bg-emerald-50 text-emerald-700'
                      : 'bg-rose-50 text-rose-700',
                  )}
                >
                  {callLog.success ? '成功' : `失败 ${callLog.code}`}
                </Badge>
                <span className="font-mono tnum text-[11.5px] text-stone-500">
                  {callLog.duration_ms}ms
                </span>
              </div>
            ) : (
              '加载中…'
            )}
          </SheetTitle>
        </SheetHeader>
        <SheetBody className="space-y-3">
          <nav className="flex items-center gap-1 border-b border-stone-200/70">
            {TABS.map(t => (
              <button
                key={t.key}
                type="button"
                onClick={() => setTab(t.key)}
                className={cn(
                  'px-3 py-1.5 text-[12.5px] font-medium transition border-b-2 -mb-[2px]',
                  tab === t.key
                    ? 'border-amber-500 text-stone-900'
                    : 'border-transparent text-stone-500 hover:text-stone-800',
                )}
              >
                {t.label}
              </button>
            ))}
          </nav>

          {tab === 'tree' ? (
            treeQ.isLoading ? (
              <div className="py-10 text-center text-sm text-stone-400">加载嵌套树…</div>
            ) : treeQ.data ? (
              <div className="space-y-2">
                <div className="text-[11px] text-stone-500">
                  以 observation 父子关系展开；点击节点可查看节点详情
                </div>
                <ObservationTree root={treeQ.data} />
              </div>
            ) : (
              <div className="py-10 text-center text-sm text-stone-400">
                无法加载嵌套树
              </div>
            )
          ) : detailQ.isLoading || !detailQ.data ? (
            <div className="py-10 text-center text-sm text-stone-400">加载中…</div>
          ) : (
            <>
              {tab === 'request' && (
                <JsonViewer value={detailQ.data.request_payload ?? {}} />
              )}
              {tab === 'response' && (
                <JsonViewer value={detailQ.data.response_payload ?? {}} />
              )}
              {tab === 'timeline' && (
                <TimelineChart
                  spans={detailQ.data.spans ?? []}
                  totalMs={detailQ.data.duration_ms}
                />
              )}
              {tab === 'logs' && (
                <div className="flex h-[280px] items-center justify-center rounded-md border border-dashed border-stone-300 text-[12px] text-stone-400">
                  日志归集二期接入；当前仅展示 spans + payload
                </div>
              )}
              {tab === 'raw' && <JsonViewer value={detailQ.data} />}
            </>
          )}

          {callLog && tab !== 'raw' && (
            <div className="border-t border-stone-200 pt-2 text-[11px] text-stone-500">
              created_at: <span className="font-mono">{formatDateTime(callLog.created_at)}</span>
              <span className="mx-2 text-stone-300">·</span>
              session: <span className="font-mono">{callLog.session_id ?? '—'}</span>
              {callLog.total_tokens != null && (
                <>
                  <span className="mx-2 text-stone-300">·</span>
                  tokens:{' '}
                  <span className="font-mono tnum">
                    {callLog.prompt_tokens}/{callLog.completion_tokens}/
                    {callLog.total_tokens}
                  </span>
                </>
              )}
            </div>
          )}
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
};

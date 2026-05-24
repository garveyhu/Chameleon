/** Trace 详情页 —— 独立路由 + 树视图 + 节点详情分屏（P22.3 PR #77） */

import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Bot, GitBranch } from 'lucide-react';
import { useEffect } from 'react';
import { useParams } from 'react-router-dom';

import { JsonViewer } from '@/core/components/common/json-viewer';
import { SectionCard } from '@/core/components/table';
import { Skeleton } from '@/core/components/common/skeleton';
import { cn } from '@/core/lib/cn';
import { useTraceStore } from '@/core/stores/trace';
import { formatDateTime } from '@/core/lib/format';
import { ObservationTree } from '@/system/call_logs/components/observation-tree';
import type { TraceTreeNode } from '@/system/call_logs/types/call-log';
import { traceApi } from '@/system/traces/services/trace';

export const TraceDetailPage = () => {
  const { requestId } = useParams<{ requestId: string }>();
  const rid = requestId ?? '';
  const selectedId = useTraceStore(s => s.selectedId);
  const select = useTraceStore(s => s.select);
  const reset = useTraceStore(s => s.reset);

  // 切 trace 时清空视图态（选中 / 折叠 / 缩放）
  useEffect(() => {
    reset();
  }, [rid, reset]);

  const treeQ = useQuery({
    queryKey: ['traces', rid, 'tree'],
    queryFn: () => traceApi.getTree(rid),
    enabled: !!rid,
  });

  if (!rid) {
    return (
      <SectionCard>
        <div className="p-6 text-sm text-stone-500">缺 request_id</div>
      </SectionCard>
    );
  }

  const root = treeQ.data;
  const focusId = selectedId ?? root?.request_id ?? '';

  return (
    <div className="space-y-3">
      <header className="flex items-center gap-3">
        <a
          href="javascript:history.back()"
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12.5px] text-stone-500 hover:bg-stone-100 hover:text-stone-800"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> 返回
        </a>
        <span className="text-stone-300">/</span>
        <div className="flex flex-1 items-baseline gap-2">
          <GitBranch className="h-3.5 w-3.5 text-stone-500" />
          <span className="text-[15px] font-medium text-stone-900">
            Trace 详情
          </span>
          <span className="font-mono text-[11px] text-stone-500">{rid}</span>
        </div>
      </header>

      {treeQ.isLoading ? (
        <Skeleton className="h-60 w-full" />
      ) : !root ? (
        <SectionCard>
          <div className="px-3 py-12 text-center text-[12px] text-stone-400">
            无法加载 trace tree
          </div>
        </SectionCard>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,2fr)_3fr]">
          <SectionCard className="!p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[11.5px] font-medium text-stone-700">
                观测嵌套树
              </span>
              <TreeStats root={root} />
            </div>
            <ObservationTree
              root={root}
              selectedId={focusId}
              onSelect={n => select(n.request_id)}
            />
          </SectionCard>

          <SectionCard className="!p-3">
            <NodeDetail
              tree={root}
              focusId={focusId}
            />
          </SectionCard>
        </div>
      )}
    </div>
  );
};

const TreeStats = ({ root }: { root: TraceTreeNode }) => {
  let totalNodes = 0;
  let okCount = 0;
  let errCount = 0;
  const walk = (n: TraceTreeNode) => {
    totalNodes += 1;
    if (n.success) okCount += 1;
    else errCount += 1;
    n.children.forEach(walk);
  };
  walk(root);
  return (
    <span className="text-[10.5px] text-stone-500">
      <span className="font-mono tnum text-stone-700">{totalNodes}</span> 节点 · {' '}
      <span className="font-mono tnum text-emerald-600">{okCount}</span> ok · {' '}
      <span className="font-mono tnum text-rose-600">{errCount}</span> err
    </span>
  );
};

interface NodeDetailProps {
  tree: TraceTreeNode;
  focusId: string;
}

const NodeDetail = ({ tree, focusId }: NodeDetailProps) => {
  const found = findNode(tree, focusId);
  const detailQ = useQuery({
    queryKey: ['traces', 'node', found?.id ?? ''],
    queryFn: () => traceApi.getNodeDetail(String(found!.id)),
    enabled: !!found,
  });

  if (!found) {
    return (
      <div className="py-12 text-center text-[12px] text-stone-400">
        左侧选一个节点
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div>
        <div className="mb-1 flex items-center gap-2 text-[11.5px]">
          <Bot className="h-3.5 w-3.5 text-stone-500" />
          <span
            className={cn(
              'rounded px-1.5 py-0.5 font-mono text-[10.5px] uppercase',
              found.success
                ? 'bg-emerald-50 text-emerald-700'
                : 'bg-rose-50 text-rose-700',
            )}
          >
            {found.observation_type}
          </span>
          <span className="font-mono text-[11px] text-stone-700">
            {found.agent_key}
          </span>
          <span className="ml-auto font-mono text-[10.5px] text-stone-500">
            {formatDateTime(found.created_at)}
          </span>
        </div>
        <div className="flex gap-3 text-[11px] text-stone-500">
          <span>
            duration:{' '}
            <span className="font-mono tnum text-stone-700">
              {found.duration_ms}ms
            </span>
          </span>
          {found.total_tokens != null && (
            <span>
              tokens:{' '}
              <span className="font-mono tnum text-stone-700">
                {found.total_tokens}
              </span>
            </span>
          )}
          {found.completion_start_ms != null && (
            <span>
              ttfb:{' '}
              <span className="font-mono tnum text-stone-700">
                {found.completion_start_ms}ms
              </span>
            </span>
          )}
        </div>
        {found.error_message && (
          <div className="mt-1 rounded border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700">
            {found.error_message}
          </div>
        )}
      </div>

      {detailQ.isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : detailQ.data ? (
        <div className="space-y-3">
          <DetailSection title="Request payload">
            <JsonViewer value={detailQ.data.request_payload ?? {}} />
          </DetailSection>
          <DetailSection title="Response payload">
            <JsonViewer value={detailQ.data.response_payload ?? {}} />
          </DetailSection>
          {detailQ.data.spans && detailQ.data.spans.length > 0 && (
            <DetailSection title="Spans">
              <ul className="space-y-1">
                {detailQ.data.spans.map((s, i) => (
                  <li
                    key={i}
                    className="rounded border border-stone-200/70 bg-white px-2 py-1 font-mono text-[11px]"
                  >
                    <span className="text-stone-700">{s.name}</span>
                    <span className="ml-2 text-stone-500">
                      {Math.round(s.end_ms - s.start_ms)}ms
                    </span>
                    <span
                      className={cn(
                        'ml-2 rounded px-1 text-[10px]',
                        s.status === 'failed'
                          ? 'bg-rose-50 text-rose-700'
                          : 'bg-emerald-50 text-emerald-700',
                      )}
                    >
                      {s.status}
                    </span>
                  </li>
                ))}
              </ul>
            </DetailSection>
          )}
        </div>
      ) : (
        <div className="py-6 text-center text-[12px] text-stone-400">
          无法加载节点详情
        </div>
      )}
    </div>
  );
};

const DetailSection = ({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) => (
  <div>
    <div className="mb-1 text-[10.5px] uppercase tracking-wider text-stone-500">
      {title}
    </div>
    {children}
  </div>
);

function findNode(
  root: TraceTreeNode,
  request_id: string,
): TraceTreeNode | null {
  if (root.request_id === request_id) return root;
  for (const ch of root.children) {
    const found = findNode(ch, request_id);
    if (found) return found;
  }
  return null;
}

/** 评估批次详情 Sheet —— metric 卡片 + per_query 明细 */

import { useQuery } from '@tanstack/react-query';
import { Check, X } from 'lucide-react';

import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import { formatDateTime } from '@/core/lib/format';
import { evaluationApi } from '@/system/kbs/services/evaluation';
import type { Evaluation } from '@/system/kbs/types/evaluation';

interface Props {
  kbId: import('@/core/types/api').EntityId;
  evalId: import('@/core/types/api').EntityId | null;
  onClose: () => void;
}

export const EvaluationDetailSheet = ({ kbId, evalId, onClose }: Props) => {
  const detailQ = useQuery({
    queryKey: ['kb-eval', kbId, evalId],
    queryFn: () => evaluationApi.get(kbId, evalId!),
    enabled: evalId != null,
    refetchInterval: query => {
      const d = query.state.data;
      return d && (d.status === 'pending' || d.status === 'running')
        ? 2000
        : false;
    },
  });

  const ev = detailQ.data ?? null;

  return (
    <Sheet
      open={evalId != null}
      onOpenChange={o => !o && onClose()}
    >
      <SheetContent width="w-[820px]">
        <SheetHeader>
          <SheetTitle>{ev ? ev.name : '加载中…'}</SheetTitle>
        </SheetHeader>
        <SheetBody className="space-y-4">
          {!ev ? (
            <div className="py-12 text-center text-sm text-stone-400">加载中…</div>
          ) : (
            <DetailBody ev={ev} />
          )}
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
};

const DetailBody = ({ ev }: { ev: Evaluation }) => {
  const res = ev.results;
  return (
    <>
      <div className="grid grid-cols-4 gap-3">
        <MetricCard label="状态" value={ev.status} />
        <MetricCard label="召回模式" value={ev.recall_mode} />
        <MetricCard label="top_k" value={String(ev.top_k)} />
        <MetricCard label="创建时间" value={formatDateTime(ev.created_at)} />
      </div>
      {ev.status === 'failed' && ev.error_message && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] text-rose-700">
          {ev.error_message}
        </div>
      )}
      {res ? (
        <>
          <div className="grid grid-cols-4 gap-3">
            {Object.entries(res.hit_at_k).map(([k, v]) => (
              <MetricCard key={k} label={`hit@${k}`} value={`${(v * 100).toFixed(1)}%`} />
            ))}
            <MetricCard label="MRR" value={res.mrr.toFixed(3)} />
            <MetricCard
              label="latency p50"
              value={`${res.latency_p50_ms.toFixed(0)}ms`}
            />
            <MetricCard
              label="latency p95"
              value={`${res.latency_p95_ms.toFixed(0)}ms`}
            />
          </div>
          <div>
            <h4 className="mb-2 text-[12.5px] font-medium text-stone-900">
              逐 query 命中（{res.per_query.length} 条）
            </h4>
            <div className="space-y-1.5">
              {res.per_query.map((pq, i) => (
                <PerQueryRow key={i} pq={pq} />
              ))}
            </div>
          </div>
        </>
      ) : (
        <div className="py-10 text-center text-sm text-stone-400">
          {ev.status === 'pending' || ev.status === 'running'
            ? '正在评估中，结果即将出现…'
            : '尚无结果'}
        </div>
      )}
    </>
  );
};

const MetricCard = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded-md border border-stone-200/70 bg-stone-50/60 px-3 py-2">
    <div className="text-[11px] text-stone-500">{label}</div>
    <div className="mt-0.5 font-mono tnum text-[13.5px] text-stone-900">
      {value}
    </div>
  </div>
);

const PerQueryRow = ({
  pq,
}: {
  pq: import('@/system/kbs/types/evaluation').EvaluationPerQuery;
}) => {
  const hit = pq.first_hit_rank != null;
  return (
    <div className="rounded-md border border-stone-200/70 bg-white px-3 py-2 text-[12px]">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={
              hit
                ? 'inline-flex h-4 w-4 items-center justify-center rounded-full bg-emerald-100 text-emerald-700'
                : 'inline-flex h-4 w-4 items-center justify-center rounded-full bg-rose-100 text-rose-700'
            }
          >
            {hit ? <Check className="h-2.5 w-2.5" /> : <X className="h-2.5 w-2.5" />}
          </span>
          <span className="text-stone-900">{pq.query}</span>
        </div>
        <span className="font-mono tnum text-[11px] text-stone-500">
          rank={pq.first_hit_rank ?? '—'} · {pq.latency_ms.toFixed(0)}ms
        </span>
      </div>
      <div className="mt-1 grid grid-cols-2 gap-2 text-[11px] text-stone-500">
        <div>
          <span className="text-stone-400">expected:</span>{' '}
          <span className="font-mono">[{pq.expected.join(', ')}]</span>
        </div>
        <div>
          <span className="text-stone-400">hits:</span>{' '}
          <span className="font-mono">[{pq.hits.join(', ')}]</span>
        </div>
      </div>
    </div>
  );
};

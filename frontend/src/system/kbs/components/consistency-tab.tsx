/** KB 详情页 · 一致性 tab —— P21.3 PR #66 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Play,
  ShieldCheck,
  Wrench,
  XCircle,
} from 'lucide-react';
import { useState } from 'react';

import { SectionCard } from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
import { cn } from '@/core/lib/cn';
import { confirm } from '@/core/lib/confirm';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { consistencyApi } from '@/system/kbs/services/consistency';
import type {
  ConsistencyIssue,
  ConsistencyReportItem,
} from '@/system/kbs/types/consistency';

interface Props {
  kbId: EntityId;
}

const ISSUE_LABEL: Record<string, { label: string; cls: string; desc: string }> = {
  orphan_chunk: {
    label: '孤儿切块',
    cls: 'bg-rose-50 text-rose-700',
    desc: '所属文档已被删除，但切块还残留在向量库里——会污染召回结果。',
  },
  dim_mismatch: {
    label: '维度不一致',
    cls: 'bg-amber-50 text-amber-700',
    desc: '向量维度与知识库配置不符（多半是换过向量模型），无法参与相似度计算。',
  },
  zero_vector: {
    label: '零向量',
    cls: 'bg-orange-50 text-orange-700',
    desc: '向量全是 0（嵌入时出错或文本为空），永远命不中、白占库。',
  },
};

const STATUS_LABEL: Record<string, { label: string; cls: string; icon: typeof CheckCircle2 }> = {
  pending: { label: '待开始', cls: 'text-stone-500', icon: Loader2 },
  running: { label: '扫描中', cls: 'text-blue-600', icon: Loader2 },
  done: { label: '已完成', cls: 'text-emerald-600', icon: CheckCircle2 },
  fixed: { label: '已修复', cls: 'text-emerald-700', icon: ShieldCheck },
  failed: { label: '失败', cls: 'text-rose-600', icon: XCircle },
};

export const ConsistencyTab = ({ kbId }: Props) => {
  const qc = useQueryClient();
  const [selectedId, setSelectedId] = useState<EntityId | null>(null);

  const listQ = useQuery({
    queryKey: ['kb-consistency', kbId],
    queryFn: () => consistencyApi.list(kbId),
    enabled: !!kbId,
  });

  const scanMut = useMutation({
    mutationFn: () => consistencyApi.scan(kbId),
    onSuccess: (report: ConsistencyReportItem) => {
      toast.success(
        `扫描完成：${report.scanned_count} chunks，${report.quarantined_count} quarantined`,
      );
      qc.invalidateQueries({ queryKey: ['kb-consistency', kbId] });
      setSelectedId(report.id);
    },
    onError: e => toast.error('扫描失败：' + (e as Error).message),
  });

  const repairMut = useMutation({
    mutationFn: (rid: EntityId) => consistencyApi.repair(kbId, rid),
    onSuccess: (report: ConsistencyReportItem) => {
      toast.success(`修复完成：物理删 ${report.fixed_count} chunks`);
      qc.invalidateQueries({ queryKey: ['kb-consistency', kbId] });
    },
    onError: e => toast.error('修复失败：' + (e as Error).message),
  });

  const handleRepair = async (report: ConsistencyReportItem) => {
    const ok = await confirm({
      title: '物理删除 quarantined chunks？',
      description: `将不可恢复地删除 ${report.quarantined_count} 个被标记的 chunks（按 reason: orphan / dim_mismatch / zero_vector）。建议先备份。`,
      confirmText: '确认删除',
      danger: true,
    });
    if (!ok) return;
    repairMut.mutate(report.id);
  };

  const selected = (listQ.data ?? []).find(r => r.id === selectedId);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-start gap-2 text-[12.5px] text-stone-600">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
          <span>
            体检向量库里「坏掉 / 用不了」的切块——孤儿切块、维度不一致、零向量，
            它们会拖累召回质量却查不出来。扫描只<span className="font-medium text-stone-800">标记隔离</span>、
            不删；确认后再「一键修复」物理删除。
          </span>
        </div>
        <Button
          size="sm"
          onClick={() => scanMut.mutate()}
          disabled={scanMut.isPending}
        >
          {scanMut.isPending ? (
            <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Play className="mr-1 h-3.5 w-3.5" />
          )}
          运行扫描
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <SectionCard className="!p-0">
          <div className="border-b border-stone-200/70 bg-warm-2/40 px-3 py-2 text-[11.5px] font-medium text-stone-600">
            扫描历史
          </div>
          <ReportList
            reports={listQ.data ?? []}
            loading={listQ.isLoading}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </SectionCard>

        <SectionCard className="!p-0">
          <div className="flex items-center justify-between border-b border-stone-200/70 bg-warm-2/40 px-3 py-2">
            <span className="text-[11.5px] font-medium text-stone-600">
              报告详情
            </span>
            {selected && selected.status === 'done' && selected.quarantined_count > 0 && (
              <Button
                size="sm"
                variant="danger"
                disabled={repairMut.isPending}
                onClick={() => handleRepair(selected)}
              >
                <Wrench className="mr-1 h-3.5 w-3.5" />
                一键修复（删 {selected.quarantined_count}）
              </Button>
            )}
          </div>
          <ReportDetail report={selected} />
        </SectionCard>
      </div>
    </div>
  );
};

const ReportList = ({
  reports,
  loading,
  selectedId,
  onSelect,
}: {
  reports: ConsistencyReportItem[];
  loading: boolean;
  selectedId: EntityId | null;
  onSelect: (id: EntityId) => void;
}) => {
  if (loading) {
    return (
      <div className="py-8 text-center text-[12px] text-stone-400">
        加载中…
      </div>
    );
  }
  if (reports.length === 0) {
    return (
      <div className="py-12 text-center text-[12px] text-stone-400">
        暂无扫描记录；点右上「运行扫描」开始
      </div>
    );
  }
  return (
    <ul className="divide-y divide-stone-100">
      {reports.map(r => {
        const sLabel = STATUS_LABEL[r.status] ?? STATUS_LABEL.done;
        return (
          <li
            key={String(r.id)}
            className={cn(
              'cursor-pointer px-3 py-2 text-[12px] hover:bg-warm-2/30',
              selectedId === r.id && 'bg-stone-50/80',
            )}
            onClick={() => onSelect(r.id)}
          >
            <div className="flex items-center justify-between">
              <span className={cn('inline-flex items-center gap-1', sLabel.cls)}>
                <sLabel.icon
                  className={cn(
                    'h-3.5 w-3.5',
                    r.status === 'running' && 'animate-spin',
                  )}
                />
                <span className="font-medium">{sLabel.label}</span>
              </span>
              <span className="text-[10.5px] text-stone-500">
                {formatDateTime(r.started_at)}
              </span>
            </div>
            <div className="mt-1 flex gap-3 text-[11px] text-stone-500">
              <span>
                扫描 <span className="font-mono tnum text-stone-700">{r.scanned_count}</span>
              </span>
              <span>
                quarantined{' '}
                <span
                  className={cn(
                    'font-mono tnum',
                    r.quarantined_count > 0 ? 'text-rose-600' : 'text-stone-700',
                  )}
                >
                  {r.quarantined_count}
                </span>
              </span>
              {r.fixed_count > 0 && (
                <span>
                  已修复{' '}
                  <span className="font-mono tnum text-emerald-700">
                    {r.fixed_count}
                  </span>
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
};

const ReportDetail = ({
  report,
}: {
  report: ConsistencyReportItem | undefined;
}) => {
  if (!report) {
    return (
      <div className="px-3 py-12 text-center text-[12px] text-stone-400">
        左侧选择一个报告查看 issues
      </div>
    );
  }
  const issues = report.issues || [];
  const byType: Record<string, ConsistencyIssue[]> = {};
  for (const it of issues) {
    (byType[it.type] ||= []).push(it);
  }

  return (
    <div className="space-y-2 px-3 py-2">
      {report.error_message && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-2 py-1.5 text-[11.5px] text-rose-700">
          <AlertTriangle className="mr-1 inline h-3.5 w-3.5" />
          {report.error_message}
        </div>
      )}
      {issues.length === 0 && report.status === 'done' && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1.5 text-[11.5px] text-emerald-700">
          <CheckCircle2 className="mr-1 inline h-3.5 w-3.5" />
          没有发现一致性问题
        </div>
      )}
      {Object.entries(byType).map(([type, list]) => {
        const meta = ISSUE_LABEL[type] ?? {
          label: type,
          cls: 'bg-stone-100 text-stone-700',
          desc: '',
        };
        return (
          <div
            key={type}
            className="rounded-md border border-stone-200/70 bg-white px-2 py-1.5"
          >
            <div className="flex items-center gap-2 text-[11.5px]">
              <span
                className={cn(
                  'rounded px-1.5 py-0.5 text-[10.5px] font-medium',
                  meta.cls,
                )}
              >
                {meta.label}
              </span>
              <span className="font-mono tnum text-stone-700">
                {list.length}
              </span>
              <span className="text-[11px] text-stone-500">条</span>
            </div>
            {meta.desc && (
              <div className="mt-1 text-[10.5px] leading-snug text-stone-500">
                {meta.desc}
              </div>
            )}
            <div className="mt-1 font-mono text-[10.5px] text-stone-500">
              chunk ids:{' '}
              {list
                .slice(0, 12)
                .map(it => it.chunk_id)
                .join(', ')}
              {list.length > 12 && ` ... 等 ${list.length - 12} 条`}
            </div>
            <div className="mt-0.5 text-[10.5px] italic text-stone-400">
              {list[0]?.reason ?? '—'}
            </div>
          </div>
        );
      })}
    </div>
  );
};

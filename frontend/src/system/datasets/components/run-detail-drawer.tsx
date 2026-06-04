/** 运行详情抽屉 —— 分数分布（可点桶过滤）+ 样本明细表 + 选中样本三栏对比。
 *  datasets（手动实验）与 eval-jobs（CI run）共用：靠 dataset_run_id 指向同一 run。
 *  内部过滤/选中态随 runId remount 重置（调用方传 key={runId}）。 */

import { useQuery } from '@tanstack/react-query';
import { Sparkles } from 'lucide-react';
import { useState } from 'react';

import { DataTable, type DataTableColumn } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { JsonEditor } from '@/core/components/ui/json-editor';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import { cn } from '@/core/lib/cn';
import { formatScore, scoreBg } from '@/core/lib/score';
import type { EntityId } from '@/core/types/api';
import { OptimizeModal } from '@/system/datasets/components/optimize-modal';
import { datasetApi } from '@/system/datasets/services/dataset';
import type {
  DatasetRunItemRow,
  MetricDistribution,
  ScoreBucket,
} from '@/system/datasets/types/dataset';

const STATUS_LABEL: Record<string, string> = {
  pending: '等待',
  running: '运行中',
  success: '成功',
  failed: '失败',
  cancelled: '已取消',
};
const statusBg = (s: string): string =>
  s === 'success'
    ? 'bg-emerald-50 text-emerald-700'
    : s === 'failed'
      ? 'bg-rose-50 text-rose-700'
      : 'bg-stone-50 text-stone-600';

const bucketColor = (low: number): string =>
  low < 0.5 ? 'bg-red-300' : low < 0.8 ? 'bg-amber-300' : 'bg-emerald-300';

const noop = () => {};

const toText = (v: unknown): string =>
  v == null ? '' : typeof v === 'string' ? v : JSON.stringify(v, null, 2);

/** 从 dict 取第一段可读文本，给明细表单元做单行预览 */
const shortText = (v: Record<string, unknown> | null | undefined): string => {
  if (v == null) return '—';
  for (const val of Object.values(v)) {
    if (typeof val === 'string' && val.trim()) return val;
  }
  return JSON.stringify(v);
};

const inputPreview = (ri: DatasetRunItemRow): string => {
  if (ri.input_preview) return ri.input_preview;
  const p = ri.input_payload;
  if (p) {
    for (const k of ['user_input', 'query', 'question', 'input', 'text']) {
      const val = p[k];
      if (typeof val === 'string') return val;
      if (val && typeof val === 'object') {
        const pv = (val as { preview?: unknown }).preview;
        if (typeof pv === 'string') return pv;
      }
    }
  }
  return '—';
};

interface Props {
  runId: EntityId | null;
  onClose: () => void;
}

export const RunDetailDrawer = ({ runId, onClose }: Props) => {
  const open = !!runId;
  const [bucket, setBucket] = useState<ScoreBucket | null>(null);
  const [sel, setSel] = useState<DatasetRunItemRow | null>(null);
  const [optimizeOpen, setOptimizeOpen] = useState(false);

  const runQ = useQuery({
    queryKey: ['ds-run', runId],
    queryFn: () => datasetApi.getRun(runId as EntityId),
    enabled: open,
  });
  const distQ = useQuery({
    queryKey: ['ds-run-dist', runId],
    queryFn: () => datasetApi.scoreDistribution(runId as EntityId),
    enabled: open,
  });
  const runItemsQ = useQuery({
    queryKey: ['ds-run-items', runId],
    queryFn: () => datasetApi.listRunItems(runId as EntityId),
    enabled: open,
  });

  const runItems = runItemsQ.data ?? [];
  const metrics = distQ.data?.metrics ?? [];
  const inBucket = (ri: DatasetRunItemRow): boolean => {
    if (!bucket || ri.score == null) return !bucket;
    return (
      ri.score >= bucket.low &&
      (ri.score < bucket.high || (bucket.high >= 1 && ri.score >= 1))
    );
  };
  const filtered = bucket ? runItems.filter(inBucket) : runItems;

  const pickBucket = (b: ScoreBucket) => {
    setBucket(prev => (prev && prev.low === b.low ? null : b));
    setSel(null);
  };

  const cols: DataTableColumn<DatasetRunItemRow>[] = [
    {
      key: 'input',
      header: '输入',
      render: ri => (
        <div className="max-w-[220px] truncate text-[11.5px] text-stone-600">
          {inputPreview(ri)}
        </div>
      ),
    },
    {
      key: 'actual',
      header: '模型回答',
      render: ri => (
        <div className="max-w-[240px] truncate text-[11.5px] text-stone-700">
          {shortText(ri.actual_output)}
        </div>
      ),
    },
    {
      key: 'score',
      header: '分数',
      align: 'right',
      width: 72,
      render: ri => (
        <span
          className={cn('rounded px-1.5 py-0.5 text-[10.5px]', scoreBg(ri.score))}
        >
          {ri.score != null ? formatScore(ri.score) : '—'}
        </span>
      ),
    },
    {
      key: 'dur',
      header: '耗时',
      align: 'right',
      width: 68,
      render: ri => (
        <span className="tnum text-[11px] text-stone-400">
          {ri.duration_ms != null ? `${ri.duration_ms}ms` : '—'}
        </span>
      ),
    },
    {
      key: 'st',
      header: '',
      align: 'center',
      width: 32,
      render: ri =>
        ri.error ? (
          <span title="执行出错" className="text-rose-500">
            ●
          </span>
        ) : null,
    },
  ];

  return (
    <Sheet open={open} onOpenChange={o => !o && onClose()}>
      <SheetContent width="w-[760px]">
        <SheetHeader>
          <SheetTitle className="text-[15px]">
            {runQ.data?.name ?? '运行详情'}
          </SheetTitle>
          {runQ.data && (
            <div className="flex items-center gap-2 text-[11.5px] text-stone-500">
              <Badge
                variant="outline"
                className={cn('text-[10.5px]', statusBg(runQ.data.status))}
              >
                {STATUS_LABEL[runQ.data.status] ?? runQ.data.status}
              </Badge>
              <span>评分器 {runQ.data.judge}</span>
              <button
                type="button"
                onClick={() => setOptimizeOpen(true)}
                className="ml-auto inline-flex items-center gap-1 rounded-md bg-violet-50 px-2 py-1 text-[11px] text-violet-700 transition hover:bg-violet-100"
              >
                <Sparkles className="h-3.5 w-3.5" /> 智能优化
              </button>
            </div>
          )}
        </SheetHeader>
        <SheetBody className="space-y-6">
          <section>
            <h4 className="mb-3 text-[12.5px] font-medium text-stone-800">
              分数分布
              <span className="ml-2 text-[10.5px] font-normal text-stone-400">
                点击柱子可筛选下方样本
              </span>
            </h4>
            {metrics.length ? (
              metrics.map(m => (
                <MetricHist
                  key={m.metric_name}
                  metric={m}
                  selected={bucket}
                  onPick={pickBucket}
                />
              ))
            ) : (
              <div className="py-4 text-center text-[11.5px] text-stone-400">
                {distQ.isLoading ? '加载中…' : '暂无评分数据'}
              </div>
            )}
          </section>

          <section>
            <div className="mb-3 flex items-center justify-between">
              <h4 className="text-[12.5px] font-medium text-stone-800">
                样本明细（{filtered.length}
                {bucket ? ` / ${runItems.length}` : ''}）
              </h4>
              {bucket && (
                <button
                  type="button"
                  onClick={() => setBucket(null)}
                  className="rounded bg-stone-100 px-2 py-0.5 text-[10.5px] text-stone-600 hover:bg-stone-200"
                >
                  分数 [{bucket.low.toFixed(1)}, {bucket.high.toFixed(1)}) ✕
                </button>
              )}
            </div>

            {sel && <ItemDetail ri={sel} onClose={() => setSel(null)} />}

            <DataTable
              columns={cols}
              rows={filtered}
              rowKey="id"
              loading={runItemsQ.isLoading}
              onRowClick={ri => setSel(ri)}
              leftBar={ri =>
                sel && sel.id === ri.id ? 'bg-stone-700' : undefined
              }
              emptyText={bucket ? '该分数区间暂无样本' : '暂无样本'}
              minWidth={620}
            />
          </section>
        </SheetBody>
        {optimizeOpen && (
          <OptimizeModal
            runId={runId as EntityId}
            onClose={() => setOptimizeOpen(false)}
          />
        )}
      </SheetContent>
    </Sheet>
  );
};

const MetricHist = ({
  metric,
  selected,
  onPick,
}: {
  metric: MetricDistribution;
  selected: ScoreBucket | null;
  onPick: (b: ScoreBucket) => void;
}) => {
  const max = Math.max(...metric.buckets.map(b => b.count), 1);
  return (
    <div className="mb-4">
      <div className="mb-1 flex items-center justify-between text-[11px]">
        <span className="text-stone-600">{metric.metric_name}</span>
        <span className="text-stone-400">
          均值 {metric.mean != null ? metric.mean.toFixed(2) : '—'}
        </span>
      </div>
      <div className="flex h-16 items-end gap-0.5">
        {metric.buckets.map((b, i) => {
          const active = !!selected && selected.low === b.low;
          const dimmed = !!selected && !active;
          return (
            <button
              key={i}
              type="button"
              onClick={() => onPick(b)}
              className="flex h-full flex-1 flex-col items-center justify-end"
              title={`[${b.low.toFixed(1)}, ${b.high.toFixed(1)}) · ${b.count} 条`}
            >
              <div
                className={cn(
                  'w-full rounded-t transition',
                  bucketColor(b.low),
                  active && 'ring-2 ring-stone-700 ring-offset-1',
                  dimmed && 'opacity-40',
                )}
                style={{ height: `${(b.count / max) * 100}%` }}
              />
            </button>
          );
        })}
      </div>
      <div className="flex justify-between text-[9px] text-stone-400">
        <span>0</span>
        <span>1</span>
      </div>
    </div>
  );
};

const ItemDetail = ({
  ri,
  onClose,
}: {
  ri: DatasetRunItemRow;
  onClose: () => void;
}) => (
  <div className="mb-3 rounded-lg border border-stone-200 bg-stone-50/40 p-3">
    <div className="mb-2 flex items-center justify-between">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[10.5px] text-stone-400">
          样本 …{String(ri.dataset_item_id).slice(-6)}
        </span>
        <span
          className={cn('rounded px-1.5 py-0.5 text-[10.5px]', scoreBg(ri.score))}
        >
          {ri.score != null ? formatScore(ri.score) : '无分'}
        </span>
        {ri.duration_ms != null && (
          <span className="text-[10.5px] text-stone-400">{ri.duration_ms}ms</span>
        )}
      </div>
      <button
        type="button"
        onClick={onClose}
        className="text-[11px] text-stone-400 hover:text-stone-700"
      >
        收起 ✕
      </button>
    </div>

    <div className="mb-2">
      <div className="mb-1 text-[10.5px] text-stone-500">输入</div>
      <JsonEditor
        value={toText(ri.input_payload)}
        onChange={noop}
        readOnly
        wrap
        label="输入"
        minHeight="56px"
        maxHeight="160px"
      />
    </div>

    <div className="mb-2 grid grid-cols-2 gap-2">
      <div>
        <div className="mb-1 text-[10.5px] text-emerald-600">理想回答</div>
        <JsonEditor
          value={toText(ri.expected_output)}
          onChange={noop}
          readOnly
          wrap
          label="预期"
          minHeight="56px"
          maxHeight="200px"
        />
      </div>
      <div>
        <div className="mb-1 text-[10.5px] text-sky-600">模型回答</div>
        <JsonEditor
          value={toText(ri.actual_output)}
          onChange={noop}
          readOnly
          wrap
          label="实际"
          minHeight="56px"
          maxHeight="200px"
        />
      </div>
    </div>

    <div>
      <div className="mb-1 text-[10.5px] text-stone-500">评分理由</div>
      {ri.score_reason ? (
        <p className="rounded border border-stone-200 bg-white px-2 py-1.5 text-[11.5px] leading-relaxed text-stone-700">
          {ri.score_reason}
        </p>
      ) : (
        <p className="rounded border border-dashed border-stone-200 px-2 py-1.5 text-[11px] text-stone-400">
          当前评分器未输出理由（升级评分体系后，AI / DSL 评分将给出逐项理由）
        </p>
      )}
    </div>

    {ri.error && (
      <div className="mt-2">
        <div className="mb-1 text-[10.5px] text-rose-500">错误</div>
        <pre className="overflow-auto rounded border border-rose-100 bg-rose-50 px-2 py-1.5 text-[10.5px] text-rose-700">
          {JSON.stringify(ri.error, null, 2)}
        </pre>
      </div>
    )}
  </div>
);

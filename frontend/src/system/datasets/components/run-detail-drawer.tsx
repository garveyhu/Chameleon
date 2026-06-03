/** 运行详情抽屉 —— 分数分布直方图 + 逐样本 预期/实际 diff。
 *  datasets（手动实验）与 eval-jobs（CI run）共用：靠 dataset_run_id 指向同一 run。 */

import { useQuery } from '@tanstack/react-query';

import { Badge } from '@/core/components/ui/badge';
import { JsonCell } from '@/core/components/ui/json-cell';
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
import { datasetApi } from '@/system/datasets/services/dataset';
import type {
  DatasetItemRow,
  DatasetRunItemRow,
  MetricDistribution,
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

interface Props {
  runId: EntityId | null;
  onClose: () => void;
}

export const RunDetailDrawer = ({ runId, onClose }: Props) => {
  const open = !!runId;
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
  const datasetId = runQ.data?.dataset_id;
  const itemsQ = useQuery({
    queryKey: ['datasets', datasetId, 'items', 'all'],
    queryFn: () => datasetApi.listItems(datasetId as EntityId, 500),
    enabled: !!datasetId,
  });

  const itemById = new Map(
    (itemsQ.data ?? []).map(it => [String(it.id), it]),
  );
  const diffs = (runItemsQ.data ?? []).map(ri => ({
    ri,
    item: itemById.get(String(ri.dataset_item_id)),
  }));
  const metrics = distQ.data?.metrics ?? [];

  return (
    <Sheet open={open} onOpenChange={o => !o && onClose()}>
      <SheetContent width="w-[720px]">
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
            </div>
          )}
        </SheetHeader>
        <SheetBody className="space-y-6">
          <section>
            <h4 className="mb-3 text-[12.5px] font-medium text-stone-800">
              分数分布
            </h4>
            {metrics.length ? (
              metrics.map(m => <MetricHist key={m.metric_name} metric={m} />)
            ) : (
              <div className="py-4 text-center text-[11.5px] text-stone-400">
                {distQ.isLoading ? '加载中…' : '暂无评分数据'}
              </div>
            )}
          </section>

          <section>
            <h4 className="mb-3 text-[12.5px] font-medium text-stone-800">
              样本明细（{diffs.length}）
            </h4>
            <div className="space-y-2">
              {diffs.map(({ ri, item }) => (
                <ItemDiff key={String(ri.id)} ri={ri} item={item} />
              ))}
              {diffs.length === 0 && (
                <div className="py-4 text-center text-[11.5px] text-stone-400">
                  {runItemsQ.isLoading ? '加载中…' : '暂无样本'}
                </div>
              )}
            </div>
          </section>
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
};

const MetricHist = ({ metric }: { metric: MetricDistribution }) => {
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
        {metric.buckets.map((b, i) => (
          <div
            key={i}
            className="flex flex-1 flex-col items-center justify-end"
            title={`[${b.low.toFixed(1)}, ${b.high.toFixed(1)}) · ${b.count} 条`}
          >
            <div
              className={cn(
                'w-full rounded-t',
                b.low < 0.5
                  ? 'bg-red-300'
                  : b.low < 0.8
                    ? 'bg-amber-300'
                    : 'bg-emerald-300',
              )}
              style={{ height: `${(b.count / max) * 100}%` }}
            />
          </div>
        ))}
      </div>
      <div className="flex justify-between text-[9px] text-stone-400">
        <span>0</span>
        <span>1</span>
      </div>
    </div>
  );
};

const ItemDiff = ({
  ri,
  item,
}: {
  ri: DatasetRunItemRow;
  item?: DatasetItemRow;
}) => (
  <div className="rounded-md border border-stone-200/70 p-2.5">
    <div className="mb-1.5 flex items-center justify-between">
      <span className="font-mono text-[10.5px] text-stone-400">
        样本 …{String(ri.dataset_item_id).slice(-6)}
      </span>
      <span
        className={cn('rounded px-1.5 py-0.5 text-[10.5px]', scoreBg(ri.score))}
      >
        {ri.score != null ? formatScore(ri.score) : '无分'}
      </span>
    </div>
    {item && (
      <div className="mb-1.5 text-[11px]">
        <span className="text-stone-400">输入 </span>
        <JsonCell value={item.input_payload} />
      </div>
    )}
    <div className="grid grid-cols-2 gap-2">
      <div className="rounded bg-stone-50 p-1.5">
        <div className="mb-0.5 text-[10px] text-stone-400">预期</div>
        <JsonCell value={item?.expected_output} className="text-[11px]" />
      </div>
      <div className="rounded bg-stone-50 p-1.5">
        <div className="mb-0.5 text-[10px] text-stone-400">实际</div>
        <JsonCell value={ri.actual_output} className="text-[11px]" />
      </div>
    </div>
    {ri.error && (
      <div className="mt-1 truncate text-[10.5px] text-rose-600">
        错误：{JSON.stringify(ri.error).slice(0, 120)}
      </div>
    )}
  </div>
);

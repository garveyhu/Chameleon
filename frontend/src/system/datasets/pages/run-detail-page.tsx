/** 运行详情整页（master-detail，URL 驱动）—— 路由 /datasets/:id/runs/:runId。
 *  左窄栏 run 列表 / 中主区 run 详情 / 右侧同屏最多 1 层覆盖物（样本详情 or 优化侧栏）。 */

import { useQuery } from '@tanstack/react-query';
import { ArrowLeft } from 'lucide-react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { cn } from '@/core/lib/cn';
import type { EntityId } from '@/core/types/api';
import { RunDetailPanel } from '@/system/datasets/components/run-detail-panel';
import { RunListRail } from '@/system/datasets/components/run-list-rail';
import { RunOptimizePanel } from '@/system/datasets/components/run-optimize-panel';
import { RunSampleDetailPanel } from '@/system/datasets/components/run-sample-detail-panel';
import { datasetApi } from '@/system/datasets/services/dataset';

export const RunDetailPage = () => {
  // ⚠️ id / runId 保留 string —— snowflake 64-bit 超 MAX_SAFE_INTEGER，Number() 丢精度
  const { id, runId } = useParams<{ id: string; runId: string }>();
  const dsId = id ?? '';
  const rid = runId ?? '';
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const itemParam = params.get('item');
  const optimizeOpen = params.get('optimize') === '1';

  const dsQ = useQuery({
    queryKey: ['datasets', dsId],
    queryFn: () => datasetApi.get(dsId),
    enabled: !!dsId,
  });
  const runsQ = useQuery({
    queryKey: ['datasets', dsId, 'runs'],
    queryFn: () => datasetApi.listRuns(dsId),
    enabled: !!dsId,
  });
  const runQ = useQuery({
    queryKey: ['ds-run', rid],
    queryFn: () => datasetApi.getRun(rid),
    enabled: !!rid,
  });
  const runItemsQ = useQuery({
    queryKey: ['ds-run-items', rid],
    queryFn: () => datasetApi.listRunItems(rid),
    enabled: !!rid,
  });

  const selectedItem =
    itemParam != null
      ? (runItemsQ.data ?? []).find(ri => String(ri.id) === itemParam) ?? null
      : null;

  const goRun = (nextRunId: EntityId) =>
    navigate(`/datasets/${dsId}/runs/${nextRunId}`);

  // push（非 replace）：切样本/优化态各进一条历史，浏览器回退能逐级区分回到上一个
  // 样本 / 收起覆盖物，而非一退就离开整个运行详情页。
  const openSample = (itemId: EntityId) => {
    const next = new URLSearchParams(params);
    next.delete('optimize');
    next.set('item', String(itemId));
    setParams(next);
  };
  const closeOverlay = () => {
    const next = new URLSearchParams(params);
    next.delete('item');
    next.delete('optimize');
    setParams(next);
  };
  const openOptimize = () => {
    const next = new URLSearchParams(params);
    next.delete('item');
    next.set('optimize', '1');
    setParams(next);
  };

  const goCompare = (ids: EntityId[]) =>
    navigate(`/datasets/${dsId}/runs/compare?ids=${ids.map(String).join(',')}`);

  if (!dsId || !rid) {
    return <div className="p-6 text-sm text-stone-500">非法的运行编号</div>;
  }

  return (
    <div className="flex h-[calc(100vh-130px)] flex-col gap-3">
      <header className="flex items-center gap-2">
        <Link
          to={`/datasets/${dsId}`}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12.5px] text-stone-500 hover:bg-stone-100 hover:text-stone-800"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> {dsQ.data?.name ?? '数据集'}
        </Link>
        <span className="text-stone-300">/</span>
        <span className="text-[13px] font-medium text-stone-900">运行详情</span>
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden rounded-xl border border-stone-200 bg-white">
        <RunListRail
          runs={runsQ.data ?? []}
          activeRunId={rid}
          loading={runsQ.isLoading}
          onSelect={goRun}
        />

        <main className={cn('min-w-0 flex-1', 'bg-[var(--color-paper)]')}>
          {runQ.isLoading ? (
            <div className="p-6 text-[12px] text-stone-400">加载运行详情…</div>
          ) : runQ.data ? (
            <RunDetailPanel
              key={rid}
              run={runQ.data}
              selectedItemId={selectedItem?.id ?? null}
              onSelectItem={ri => openSample(ri.id)}
              onOptimize={openOptimize}
              onCompareParent={goCompare}
            />
          ) : (
            <div className="p-6 text-[12px] text-stone-400">未找到该运行</div>
          )}
        </main>

        {selectedItem && (
          <RunSampleDetailPanel ri={selectedItem} onClose={closeOverlay} />
        )}
        {optimizeOpen && runQ.data && (
          <RunOptimizePanel
            runId={rid}
            datasetId={runQ.data.dataset_id}
            onClose={closeOverlay}
            onApplied={goRun}
          />
        )}
      </div>
    </div>
  );
};

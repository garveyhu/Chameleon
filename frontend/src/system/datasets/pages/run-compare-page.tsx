/** 运行对比整页（URL 驱动）—— 路由 /datasets/:id/runs/compare?ids=a,b,c。
 *  多版本对比 = URL 带多个 id；对比上一版本 = ?ids=parent,child。复用 RunCompareMatrix。 */

import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, GitCompare } from 'lucide-react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { RunCompareMatrix } from '@/system/datasets/components/run-compare-matrix';
import { datasetApi } from '@/system/datasets/services/dataset';
import type { EntityId } from '@/core/types/api';

const parseIds = (raw: string | null): EntityId[] => {
  if (!raw) return [];
  return raw
    .split(',')
    .map(s => s.trim())
    .filter(Boolean);
};

export const RunComparePage = () => {
  // ⚠️ dsId / run ids 保留 string —— snowflake 64-bit 超 MAX_SAFE_INTEGER
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const dsId = id ?? '';
  const [params] = useSearchParams();
  const runIds = parseIds(params.get('ids'));

  // 对比页是从运行详情 / 运行 tab 进来的叶子页，面包屑做真·上一步回退，
  // 直链落地无历史时兜回数据集运行 tab，而非写死目标。
  const goBack = () => {
    if (window.history.length > 1) navigate(-1);
    else navigate(`/datasets/${dsId}?tab=runs`);
  };

  const dsQ = useQuery({
    queryKey: ['datasets', dsId],
    queryFn: () => datasetApi.get(dsId),
    enabled: !!dsId,
  });

  return (
    <div className="space-y-3">
      <header className="flex items-center gap-2">
        <button
          type="button"
          onClick={goBack}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12.5px] text-stone-500 hover:bg-stone-100 hover:text-stone-800"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> {dsQ.data?.name ?? '数据集'}
        </button>
        <span className="text-stone-300">/</span>
        <span className="inline-flex items-center gap-1.5 text-[13px] font-medium text-stone-900">
          <GitCompare className="h-3.5 w-3.5 text-stone-500" /> 运行对比
        </span>
        <span className="text-[11.5px] text-stone-400">· {runIds.length} 个运行</span>
      </header>

      {runIds.length < 2 ? (
        <div className="rounded-xl border border-dashed border-stone-200 py-12 text-center text-[12.5px] text-stone-400">
          至少选 2 个运行才能对比；从运行详情页「对比上一版本」或运行列表「对比所选」进入
        </div>
      ) : (
        <RunCompareMatrix runIds={runIds} />
      )}
    </div>
  );
};

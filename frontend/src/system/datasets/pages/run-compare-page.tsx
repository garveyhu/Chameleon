/** 运行对比整页（URL 驱动）—— 路由 /datasets/:id/runs/compare?ids=a,b,c。
 *  多版本对比 = URL 带多个 id；对比上一版本 = ?ids=parent,child。复用 RunCompareMatrix。 */

import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft,
  GitCompare,
  Image as ImageIcon,
  Loader2,
  Sheet,
} from 'lucide-react';
import { useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import {
  RunCompareMatrix,
  type RunCompareHandle,
} from '@/system/datasets/components/run-compare-matrix';
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

  const matrixRef = useRef<RunCompareHandle>(null);
  const [exporting, setExporting] = useState(false);

  const exportBtn =
    'inline-flex items-center gap-1 rounded-md border border-stone-200 bg-white px-2.5 py-1 text-[11.5px] font-medium text-stone-600 transition hover:border-stone-300 hover:text-stone-800 disabled:opacity-60';

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

        {runIds.length >= 2 && (
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={() => matrixRef.current?.exportImage()}
              disabled={exporting}
              title="把对比统计（图表 + AI 分析）和得分表导出为图片，方便分享"
              className={exportBtn}
            >
              {exporting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <ImageIcon className="h-3.5 w-3.5 text-stone-400" />
              )}
              {exporting ? '导出中…' : '导出图片'}
            </button>
            <button
              type="button"
              onClick={() => matrixRef.current?.exportExcel()}
              disabled={exporting}
              title="把逐题明细（各模型得分 + 输出）导出为 Excel"
              className={exportBtn}
            >
              <Sheet className="h-3.5 w-3.5 text-stone-400" />
              导出数据
            </button>
          </div>
        )}
      </header>

      {runIds.length < 2 ? (
        <div className="rounded-xl border border-dashed border-stone-200 py-12 text-center text-[12.5px] text-stone-400">
          至少选 2 个运行才能对比；从运行详情页「对比上一版本」或运行列表「对比所选」进入
        </div>
      ) : (
        <RunCompareMatrix
          ref={matrixRef}
          runIds={runIds}
          datasetName={dsQ.data?.name}
          onExportingChange={setExporting}
        />
      )}
    </div>
  );
};

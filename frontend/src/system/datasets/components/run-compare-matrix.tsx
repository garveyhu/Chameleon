/** 运行对比矩阵 —— 借鉴 Langfuse：样本行 × 运行列，score 色块热力图，
 *  点单格看该样本在该运行下的 预期/实际 diff。 */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { JsonCell } from '@/core/components/ui/json-cell';
import { cn } from '@/core/lib/cn';
import { formatScore, scoreBg } from '@/core/lib/score';
import type { EntityId } from '@/core/types/api';
import { datasetApi } from '@/system/datasets/services/dataset';
import type { DatasetRunRow } from '@/system/datasets/types/dataset';

const runMean = (r: DatasetRunRow): number | null => {
  const s = r.summary as Record<string, unknown> | null;
  const v = s?.mean_score ?? s?.mean ?? s?.avg_score;
  return typeof v === 'number' ? v : null;
};

interface Props {
  runIds: EntityId[];
}

export const RunCompareMatrix = ({ runIds }: Props) => {
  const q = useQuery({
    queryKey: ['ds-compare', [...runIds].sort()],
    queryFn: () => datasetApi.compareRuns(runIds),
    enabled: runIds.length >= 2,
  });
  const [sel, setSel] = useState<{ itemId: string; runId: string } | null>(
    null,
  );

  if (q.isLoading) {
    return (
      <div className="py-8 text-center text-[12px] text-stone-400">
        加载对比…
      </div>
    );
  }
  const data = q.data;
  if (!data) return null;
  const { runs, rows } = data;

  const selRow = sel
    ? rows.find(r => String(r.dataset_item_id) === sel.itemId)
    : null;
  const selCell = selRow && sel ? selRow.cells[sel.runId] : undefined;
  const selRun = sel ? runs.find(r => String(r.id) === sel.runId) : null;

  return (
    <div className="space-y-3">
      <div className="overflow-auto rounded-lg border border-stone-200">
        <table className="w-full border-collapse text-[11.5px]">
          <thead>
            <tr className="bg-stone-50">
              <th className="sticky left-0 z-10 min-w-[220px] border-b border-r border-stone-200 bg-stone-50 px-3 py-2 text-left font-medium text-stone-500">
                样本 · 预期
              </th>
              {runs.map(run => {
                const m = runMean(run);
                return (
                  <th
                    key={String(run.id)}
                    className="min-w-[116px] border-b border-stone-200 px-3 py-2 text-left font-medium text-stone-600"
                  >
                    <div className="truncate" title={run.name}>
                      {run.name}
                    </div>
                    <div className="mt-0.5 text-[10px] text-stone-400">
                      均值 {m != null ? formatScore(m) : '—'}
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map(row => {
              const itemId = String(row.dataset_item_id);
              return (
                <tr key={itemId} className="hover:bg-stone-50/40">
                  <td className="sticky left-0 z-10 max-w-[260px] border-b border-r border-stone-200 bg-white px-3 py-2 align-top">
                    <div
                      className="truncate text-stone-700"
                      title={row.input_preview ?? ''}
                    >
                      {row.input_preview ?? (
                        <span className="text-stone-300">（无预览）</span>
                      )}
                    </div>
                    {row.expected_output != null && (
                      <div className="mt-0.5 truncate text-[10px] text-stone-400">
                        预期 {JSON.stringify(row.expected_output).slice(0, 40)}
                      </div>
                    )}
                  </td>
                  {runs.map(run => {
                    const runId = String(run.id);
                    const cell = row.cells[runId];
                    const active =
                      sel?.itemId === itemId && sel?.runId === runId;
                    return (
                      <td
                        key={runId}
                        className="border-b border-stone-100 px-1.5 py-1.5 align-top"
                      >
                        {cell ? (
                          <button
                            type="button"
                            onClick={() =>
                              setSel(active ? null : { itemId, runId })
                            }
                            className={cn(
                              'tnum w-full rounded px-2 py-1 text-left transition',
                              scoreBg(cell.score),
                              active && 'ring-2 ring-stone-400',
                            )}
                          >
                            {cell.score != null
                              ? formatScore(cell.score)
                              : cell.error
                                ? '错误'
                                : '—'}
                          </button>
                        ) : (
                          <span className="pl-2 text-stone-300">—</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td
                  colSpan={runs.length + 1}
                  className="px-3 py-8 text-center text-stone-400"
                >
                  无样本
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {sel && selCell && (
        <div className="rounded-lg border border-stone-200 p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[12px] font-medium text-stone-700">
              样本 …{sel.itemId.slice(-6)} · {selRun?.name}
            </span>
            <span
              className={cn(
                'rounded px-1.5 py-0.5 text-[11px]',
                scoreBg(selCell.score),
              )}
            >
              {selCell.score != null ? formatScore(selCell.score) : '无分'}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded bg-stone-50 p-2">
              <div className="mb-0.5 text-[10px] text-stone-400">预期</div>
              <JsonCell
                value={selRow?.expected_output}
                className="text-[11px]"
              />
            </div>
            <div className="rounded bg-stone-50 p-2">
              <div className="mb-0.5 text-[10px] text-stone-400">实际</div>
              <JsonCell value={selCell.actual_output} className="text-[11px]" />
            </div>
          </div>
          {selCell.error != null && (
            <div className="mt-1 text-[10.5px] text-rose-600">
              错误：{JSON.stringify(selCell.error).slice(0, 160)}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

/** 智能优化侧栏 —— 整页右侧滑出（非 modal 盖 drawer）。
 *  原 Prompt + 报告 + 优化后 Prompt 并排；「用优化后 Prompt 跑新一轮」保留。 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, Play, Sparkles, X } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/core/components/ui/button';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { datasetApi } from '@/system/datasets/services/dataset';
import type { OptimizeResult } from '@/system/datasets/types/dataset';

interface Props {
  runId: EntityId;
  datasetId: EntityId;
  onClose: () => void;
  /** 重跑出新一轮后跳到该新 run 整页详情。 */
  onApplied: (newRunId: EntityId) => void;
}

export const RunOptimizePanel = ({ runId, datasetId, onClose, onApplied }: Props) => {
  const qc = useQueryClient();
  const [result, setResult] = useState<OptimizeResult | null>(null);

  const mut = useMutation({
    mutationFn: () => datasetApi.optimizeRun(runId),
    onSuccess: setResult,
    onError: (e: unknown) =>
      toast.error((e as { message?: string })?.message || '优化失败'),
  });

  const applyMut = useMutation({
    mutationFn: () => datasetApi.applyOptimized(runId),
    onSuccess: run => {
      toast.success(`已用优化 Prompt 跑出新一轮「${run.name}」`);
      qc.invalidateQueries({ queryKey: ['datasets', datasetId, 'runs'] });
      onApplied(run.id);
    },
    onError: (e: unknown) =>
      toast.error((e as { message?: string })?.message || '应用失败'),
  });

  return (
    <aside className="flex h-full w-[560px] shrink-0 flex-col overflow-hidden border-l border-stone-200 bg-[var(--color-paper)]">
      <header className="flex items-start justify-between border-b border-stone-200 px-4 py-3">
        <div>
          <h3 className="flex items-center gap-1.5 text-[14px] font-medium text-stone-900">
            <Sparkles className="h-4 w-4 text-violet-500" /> 智能优化 Prompt
          </h3>
          <p className="mt-0.5 text-[11px] text-stone-500">
            汇总低分样本共性缺陷，让 AI 重写 System Prompt（走评测渠道，成本进 Trace）
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          title="收起"
          className="rounded p-1 text-stone-400 hover:bg-stone-100 hover:text-stone-700"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </header>

      <div className="flex-1 space-y-4 overflow-auto px-4 py-3">
        {!result ? (
          <div className="flex flex-col items-center gap-3 py-12">
            <p className="text-[12px] text-stone-500">
              基于低分样本分析并重写 Prompt，可能需要 10–30 秒。
            </p>
            <Button size="sm" disabled={mut.isPending} onClick={() => mut.mutate()}>
              {mut.isPending ? (
                <>
                  <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> 分析 + 重写中…
                </>
              ) : (
                <>
                  <Sparkles className="mr-1 h-3.5 w-3.5" /> 开始智能优化
                </>
              )}
            </Button>
          </div>
        ) : (
          <>
            <div>
              <div className="mb-1 flex items-baseline gap-2">
                <span className="text-[12px] font-medium text-stone-800">优化报告</span>
                <span className="text-[10.5px] text-stone-400">
                  基于 {result.weak_count} 条低分样本
                </span>
              </div>
              <p className="whitespace-pre-wrap rounded-lg border border-stone-200 bg-stone-50/50 p-3 text-[12px] leading-relaxed text-stone-700">
                {result.report || '（无报告）'}
              </p>
            </div>
            <div>
              <div className="mb-1 text-[12px] font-medium text-stone-800">
                Prompt 前后对比
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="mb-1 text-[10.5px] text-stone-500">原 Prompt</div>
                  <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap rounded-md border border-stone-200 bg-stone-50/50 p-2 text-[11.5px] leading-relaxed text-stone-600">
                    {result.original_prompt || '（空，模型直调无系统提示）'}
                  </pre>
                </div>
                <div>
                  <div className="mb-1 text-[10.5px] text-emerald-600">优化后 Prompt</div>
                  <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap rounded-md border border-emerald-200 bg-emerald-50/40 p-2 text-[11.5px] leading-relaxed text-stone-700">
                    {result.optimized_prompt || '（空）'}
                  </pre>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {result && (
        <footer className="flex items-center justify-end gap-2 border-t border-stone-200 px-4 py-3">
          <p className="mr-auto text-[10.5px] text-stone-400">
            用优化后的 Prompt 重跑整个数据集，落为新一轮运行（同步评测，数十秒）
          </p>
          <Button
            size="sm"
            disabled={applyMut.isPending || !result.optimized_prompt?.trim()}
            onClick={() => applyMut.mutate()}
          >
            {applyMut.isPending ? (
              <>
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> 评测进行中…数十秒
              </>
            ) : (
              <>
                <Play className="mr-1 h-3.5 w-3.5" /> 用优化后 Prompt 跑新一轮
              </>
            )}
          </Button>
        </footer>
      )}
    </aside>
  );
};

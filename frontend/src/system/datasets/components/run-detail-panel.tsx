/** 运行详情主区 —— run 头部（状态/judge/均分/版本徽标 + 动作）+ 分数分布桶 + 样本明细表。
 *  样本选中 / 优化由上层整页管理（侧栏滑出），本组件只出内容 + 回调。 */

import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, GitCompare, Sparkles } from 'lucide-react';
import { useState } from 'react';

import { DataTable, type DataTableColumn } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { cn } from '@/core/lib/cn';
import { formatScore, scoreBg } from '@/core/lib/score';
import type { EntityId } from '@/core/types/api';
import { RunScoreDistribution } from '@/system/datasets/components/run-score-distribution';
import { datasetApi } from '@/system/datasets/services/dataset';
import { judgeLabel } from '@/system/datasets/utils/judge-meta';
import { verdictOf } from '@/system/datasets/utils/verdict';
import type {
  DatasetRunDetail,
  DatasetRunItemRow,
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

const runMean = (run: DatasetRunDetail): number | null => {
  const s = run.summary as Record<string, unknown> | null;
  const v = s?.mean_score ?? s?.mean ?? s?.avg_score;
  return typeof v === 'number' ? v : null;
};

interface Props {
  run: DatasetRunDetail;
  selectedItemId: EntityId | null;
  onSelectItem: (ri: DatasetRunItemRow) => void;
  onOptimize: () => void;
  /** 「对比上一版本」：把 [parentRunId, runId] 喂进对比整页（父已删则不渲染按钮）。 */
  onCompareParent: (runIds: EntityId[]) => void;
}

export const RunDetailPanel = ({
  run,
  selectedItemId,
  onSelectItem,
  onOptimize,
  onCompareParent,
}: Props) => {
  const [bucket, setBucket] = useState<ScoreBucket | null>(null);
  // 评估配置区默认折叠（多数时候看分数 / 样本，配置按需展开）
  const [configOpen, setConfigOpen] = useState(false);

  const distQ = useQuery({
    queryKey: ['ds-run-dist', run.id],
    queryFn: () => datasetApi.scoreDistribution(run.id),
  });
  const runItemsQ = useQuery({
    queryKey: ['ds-run-items', run.id],
    queryFn: () => datasetApi.listRunItems(run.id),
  });

  const runItems = runItemsQ.data ?? [];
  const metrics = distQ.data?.metrics ?? [];
  const mean = runMean(run);

  // 本次配置：裁判模型 / 评分要点（judge_config）+ 系统提示词（prompt_override）
  const jc = run.judge_config ?? {};
  const judgeModel = typeof jc.judge_model === 'string' ? jc.judge_model : '';
  const criteria = typeof jc.criteria === 'string' ? jc.criteria : '';

  const inBucket = (ri: DatasetRunItemRow): boolean => {
    if (!bucket || ri.score == null) return !bucket;
    return (
      ri.score >= bucket.low &&
      (ri.score < bucket.high || (bucket.high >= 1 && ri.score >= 1))
    );
  };
  const filtered = bucket ? runItems.filter(inBucket) : runItems;

  const pickBucket = (b: ScoreBucket) =>
    setBucket(prev => (prev && prev.low === b.low ? null : b));

  const cols: DataTableColumn<DatasetRunItemRow>[] = [
    {
      key: 'input',
      header: '输入',
      render: ri => (
        <div className="max-w-[260px] truncate text-[11.5px] text-stone-600">
          {inputPreview(ri)}
        </div>
      ),
    },
    {
      key: 'actual',
      header: '模型回答',
      render: ri => (
        <div className="max-w-[280px] truncate text-[11.5px] text-stone-700">
          {shortText(ri.actual_output)}
        </div>
      ),
    },
    {
      key: 'score',
      header: '分数',
      align: 'right',
      width: 96,
      render: ri => {
        const verdict = verdictOf(ri.field_scores);
        return (
          <span className="inline-flex items-center justify-end gap-1">
            {verdict && (
              <Badge variant={verdict.variant} className="px-1 py-0 text-[10px]">
                {verdict.label}
              </Badge>
            )}
            <span className={cn('rounded px-1.5 py-0.5 text-[10.5px]', scoreBg(ri.score))}>
              {ri.score != null ? formatScore(ri.score) : '—'}
            </span>
          </span>
        );
      },
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
    <div className="flex h-full flex-col overflow-hidden">
      <header className="border-b border-stone-200 px-5 py-3.5">
        <div className="flex items-center gap-2">
          <h2 className="text-[16px] font-medium text-stone-900">{run.name}</h2>
          {run.parent_run_id != null && (
            <Badge variant="outline" className="bg-violet-50 text-[10.5px] text-violet-700">
              ← 优化自上一版本
            </Badge>
          )}
          <div className="ml-auto flex items-center gap-2">
            {run.parent_run_id != null && (
              <button
                type="button"
                onClick={() => onCompareParent([run.parent_run_id as EntityId, run.id])}
                className="inline-flex items-center gap-1 rounded-md bg-stone-50 px-2 py-1 text-[11px] text-stone-700 transition hover:bg-stone-100"
              >
                <GitCompare className="h-3.5 w-3.5" /> 对比上一版本
              </button>
            )}
            {/* 智能优化只对模型直调运行有意义：它重写 System Prompt 再重跑。
                智能体的 Prompt 烤在其工作流编排里，外部无法覆盖，故禁用入口。 */}
            <button
              type="button"
              onClick={onOptimize}
              disabled={!!run.agent_key}
              title={
                run.agent_key
                  ? '本次被测对象是智能体，其 Prompt 在工作流编排里维护，智能优化仅用于模型直调运行；如需优化请到工作流编辑器调整后重新评测'
                  : '汇总低分样本，让 AI 重写 System Prompt'
              }
              className="inline-flex items-center gap-1 rounded-md bg-violet-50 px-2 py-1 text-[11px] text-violet-700 transition hover:bg-violet-100 disabled:cursor-not-allowed disabled:bg-stone-50 disabled:text-stone-400"
            >
              <Sparkles className="h-3.5 w-3.5" /> 智能优化
            </button>
          </div>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11.5px] text-stone-500">
          <Badge variant="outline" className={cn('text-[10.5px]', statusBg(run.status))}>
            {STATUS_LABEL[run.status] ?? run.status}
          </Badge>
          <span>评分器 {judgeLabel(run.judge)}</span>
          {run.model_override && <span>· 模型 {run.model_override}</span>}
          {mean != null && (
            <span>
              · 均分 <span className="tnum font-medium text-stone-700">{formatScore(mean)}</span>
            </span>
          )}
        </div>
      </header>

      <div className="flex-1 space-y-6 overflow-auto px-5 py-4">
        <section>
          <button
            type="button"
            onClick={() => setConfigOpen(o => !o)}
            className="flex items-center gap-1 text-[12.5px] font-medium text-stone-800 transition hover:text-stone-900"
          >
            {configOpen ? (
              <ChevronDown className="h-3.5 w-3.5 text-stone-400" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 text-stone-400" />
            )}
            评估配置
          </button>
          {configOpen && (
          <div className="mt-2 space-y-2 rounded-md border border-stone-200/70 bg-stone-50/40 p-3 text-[11.5px]">
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-stone-600">
              {run.agent_key ? (
                <span>
                  被测智能体{' '}
                  <span className="font-mono text-stone-800">
                    {run.agent_key}
                  </span>
                </span>
              ) : (
                <span>
                  被测模型{' '}
                  <span className="font-mono text-stone-800">
                    {run.model_override || '数据集默认'}
                  </span>
                </span>
              )}
              <span>
                评分器{' '}
                <span className="text-stone-800">{judgeLabel(run.judge)}</span>
              </span>
              {judgeModel && (
                <span>
                  裁判模型{' '}
                  <span className="font-mono text-stone-800">{judgeModel}</span>
                </span>
              )}
            </div>
            {criteria && (
              <div>
                <div className="mb-0.5 text-[10px] text-stone-400">评分要点</div>
                <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-words rounded bg-white p-2 font-mono text-[11px] leading-relaxed text-stone-700">
                  {criteria}
                </pre>
              </div>
            )}
            {run.prompt_override ? (
              <div>
                <div className="mb-0.5 text-[10px] text-stone-400">
                  系统提示词
                </div>
                <pre className="max-h-44 overflow-auto whitespace-pre-wrap break-words rounded bg-white p-2 font-mono text-[11px] leading-relaxed text-stone-700">
                  {run.prompt_override}
                </pre>
              </div>
            ) : null}
          </div>
          )}
        </section>

        <section>
          <h4 className="mb-3 text-[12.5px] font-medium text-stone-800">
            分数分布
            <span className="ml-2 text-[10.5px] font-normal text-stone-400">
              点击柱子可筛选下方样本
            </span>
          </h4>
          <RunScoreDistribution
            metrics={metrics}
            selected={bucket}
            onPick={pickBucket}
            loading={distQ.isLoading}
          />
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
          <DataTable
            columns={cols}
            rows={filtered}
            rowKey="id"
            loading={runItemsQ.isLoading}
            onRowClick={ri => onSelectItem(ri)}
            leftBar={ri =>
              selectedItemId != null && String(selectedItemId) === String(ri.id)
                ? 'bg-stone-700'
                : undefined
            }
            emptyText={bucket ? '该分数区间暂无样本' : '暂无样本'}
            minWidth={620}
          />
        </section>
      </div>
    </div>
  );
};

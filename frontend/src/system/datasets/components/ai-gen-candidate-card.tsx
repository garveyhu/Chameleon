/** 评审态单条候选卡片 —— 勾选 + 行内编辑 + AI 优化 / 重新生成 / 删除。 */

import { Loader2, RefreshCw, Sparkles, Trash2 } from 'lucide-react';

import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import type { AiGenCandidate } from '@/system/datasets/types/dataset';

interface Props {
  candidate: AiGenCandidate;
  index: number;
  /** optimize / regenerate 进行中（按钮转圈 + 禁用整卡操作）。 */
  refining: boolean;
  onToggle: (cid: string) => void;
  onChangeInput: (cid: string, value: string) => void;
  onChangeAnswer: (cid: string, value: string) => void;
  onOptimize: (cid: string) => void;
  onRegenerate: (cid: string) => void;
  onRemove: (cid: string) => void;
}

export const AiGenCandidateCard = ({
  candidate,
  index,
  refining,
  onToggle,
  onChangeInput,
  onChangeAnswer,
  onOptimize,
  onRegenerate,
  onRemove,
}: Props) => {
  const { cid, user_input, answer, selected } = candidate;

  return (
    <div
      className={cn(
        'rounded-lg border bg-white p-3 transition',
        selected ? 'border-primary-300 ring-1 ring-primary-100' : 'border-stone-200',
        refining && 'opacity-70',
      )}
    >
      <div className="mb-2 flex items-center gap-2">
        <input
          type="checkbox"
          aria-label={`选择候选 ${index + 1}`}
          checked={selected}
          onChange={() => onToggle(cid)}
          className="h-3.5 w-3.5 accent-primary-600"
        />
        <span className="text-[11px] font-medium text-stone-500">候选 #{index + 1}</span>
        {refining && (
          <span className="inline-flex items-center gap-1 text-[10.5px] text-primary-600">
            <Loader2 className="h-3 w-3 animate-spin" /> 处理中…
          </span>
        )}
        <span className="ml-auto inline-flex items-center gap-1">
          <button
            type="button"
            disabled={refining}
            onClick={() => onOptimize(cid)}
            title="AI 优化（在原候选基础上改写提升质量）"
            className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-[10.5px] text-violet-600 hover:bg-violet-50 disabled:opacity-50"
          >
            <Sparkles className="h-3 w-3" /> AI 优化
          </button>
          <button
            type="button"
            disabled={refining}
            onClick={() => onRegenerate(cid)}
            title="重新生成（同主题另起一条不同候选）"
            className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-[10.5px] text-stone-500 hover:bg-stone-100 disabled:opacity-50"
          >
            <RefreshCw className="h-3 w-3" /> 重新生成
          </button>
          <button
            type="button"
            disabled={refining}
            onClick={() => onRemove(cid)}
            title="删除该候选"
            className="rounded p-1 text-stone-300 hover:bg-rose-50 hover:text-rose-600 disabled:opacity-50"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </span>
      </div>

      <div className="space-y-2">
        <div>
          <label className="mb-1 block text-[10.5px] font-medium text-stone-500">问题</label>
          <Textarea
            value={user_input}
            disabled={refining}
            onChange={e => onChangeInput(cid, e.target.value)}
            rows={2}
            className="min-h-[40px] text-[12px]"
          />
        </div>
        <div>
          <label className="mb-1 block text-[10.5px] font-medium text-stone-500">理想回答</label>
          <Textarea
            value={answer}
            disabled={refining}
            onChange={e => onChangeAnswer(cid, e.target.value)}
            rows={3}
            className="min-h-[56px] text-[12px]"
          />
        </div>
      </div>
    </div>
  );
};

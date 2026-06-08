/** 流式 AI 扩样 + 候选评审 Studio（替代旧 ai-generate-modal）。
 *
 * 三态状态机：
 *  - form：任务描述 + 数量 → 「生成」
 *  - streaming：实时滚动原文（delta 累加，typing 感）+ 候选卡片随 candidate chunk 浮现，可「停止」
 *  - review：候选卡片列表（勾选 / 行内编辑 / AI 优化 / 重新生成 / 删除），导入选中
 *
 * 生成与入库解耦：流式期间不落库，用户挑拣 / 编辑 / 优化后再 bulkImport 导入选中。
 */

import { useMemo, useRef, useState } from 'react';

import { Sparkles, Square } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { Modal, ModalContent, ModalFooter, ModalHeader, ModalTitle } from '@/core/components/ui/modal';
import { NeonLoader } from '@/core/components/ui/neon-loader';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { AiGenCandidateCard } from '@/system/datasets/components/ai-gen-candidate-card';
import { datasetApi } from '@/system/datasets/services/dataset';
import type {
  AiGenCandidate,
  AiGenStreamChunk,
  BulkImportItem,
  CategoryDef,
} from '@/system/datasets/types/dataset';

interface Props {
  datasetId: EntityId;
  /** 数据集能力维度（候选卡显示 AI 自动归类的标签） */
  categories?: CategoryDef[];
  onClose: () => void;
  onDone: () => void;
}

type Stage = 'form' | 'streaming' | 'review';

interface DeltaData {
  text?: string;
}
interface CandidateData {
  user_input?: string;
  answer?: string;
  note?: string;
  category?: string | null;
}

export const AiGenerateStudio = ({
  datasetId,
  categories,
  onClose,
  onDone,
}: Props) => {
  const [stage, setStage] = useState<Stage>('form');
  const [task, setTask] = useState('');
  const [count, setCount] = useState(5);

  const [streamText, setStreamText] = useState('');
  const [candidates, setCandidates] = useState<AiGenCandidate[]>([]);
  const [refiningCids, setRefiningCids] = useState<Set<string>>(() => new Set());
  const [importing, setImporting] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  // 候选 cid 自增计数器（禁 Math.random，保证渲染顺序稳定）。
  const cidCounter = useRef(0);
  const nextCid = (): string => `c${cidCounter.current++}`;

  const selectedCount = useMemo(() => candidates.filter(c => c.selected).length, [candidates]);
  const allSelected = candidates.length > 0 && selectedCount === candidates.length;

  const handleChunk = (chunk: AiGenStreamChunk) => {
    // sse_response 兜底异常时发的是信封 {"error":{type,message}}（无 type 键），
    // 与业务 chunk {type,data} 不同形态，单独识别避免错误被静默吞掉。
    const envelope = (chunk as { error?: { message?: string } }).error;
    if (envelope) {
      toast.error(envelope.message || '生成出错，请重试');
      return;
    }
    if (chunk.type === 'delta') {
      const text = (chunk.data as DeltaData)?.text ?? '';
      if (text) setStreamText(prev => prev + text);
    } else if (chunk.type === 'candidate') {
      const d = chunk.data as CandidateData;
      setCandidates(prev => [
        ...prev,
        {
          cid: nextCid(),
          user_input: d.user_input ?? '',
          answer: d.answer ?? '',
          note: d.note ?? '',
          category: d.category ?? null,
          selected: true,
        },
      ]);
    } else if (chunk.type === 'error') {
      const msg =
        (chunk.data as { message?: string })?.message ?? '生成出错，请重试';
      toast.error(msg);
    }
  };

  const startStream = async () => {
    if (!task.trim()) {
      toast.error('请填写生成任务描述');
      return;
    }
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    cidCounter.current = 0;
    setStreamText('');
    setCandidates([]);
    setStage('streaming');
    try {
      await datasetApi.aiGenerateStream(
        datasetId,
        { task_description: task.trim(), count },
        { signal: ctrl.signal, onChunk: handleChunk },
      );
    } catch (e) {
      if (ctrl.signal.aborted) {
        // 用户主动停止：保留已生成候选进评审态。
      } else {
        toast.error((e as { message?: string })?.message || '生成失败');
      }
    } finally {
      abortRef.current = null;
      setStage('review');
    }
  };

  const stopStream = () => {
    abortRef.current?.abort();
  };

  const regenerateAll = () => {
    void startStream();
  };

  const toggleOne = (cid: string) =>
    setCandidates(prev =>
      prev.map(c => (c.cid === cid ? { ...c, selected: !c.selected } : c)),
    );
  const toggleAll = () =>
    setCandidates(prev => prev.map(c => ({ ...c, selected: !allSelected })));
  const changeInput = (cid: string, value: string) =>
    setCandidates(prev =>
      prev.map(c => (c.cid === cid ? { ...c, user_input: value } : c)),
    );
  const changeAnswer = (cid: string, value: string) =>
    setCandidates(prev =>
      prev.map(c => (c.cid === cid ? { ...c, answer: value } : c)),
    );
  const changeNote = (cid: string, value: string) =>
    setCandidates(prev =>
      prev.map(c => (c.cid === cid ? { ...c, note: value } : c)),
    );
  const removeOne = (cid: string) =>
    setCandidates(prev => prev.filter(c => c.cid !== cid));

  const refine = async (cid: string, mode: 'optimize' | 'regenerate') => {
    const target = candidates.find(c => c.cid === cid);
    if (!target) return;
    setRefiningCids(prev => new Set(prev).add(cid));
    try {
      const refined = await datasetApi.refineCandidate(datasetId, {
        task_description: task.trim(),
        candidate: {
          user_input: target.user_input,
          answer: target.answer,
          note: target.note,
          category: target.category,
        },
        mode,
      });
      setCandidates(prev =>
        prev.map(c =>
          c.cid === cid
            ? {
                ...c,
                user_input: refined.user_input,
                answer: refined.answer ?? '',
                note: refined.note ?? c.note,
                category: refined.category ?? c.category,
              }
            : c,
        ),
      );
    } catch (e) {
      toast.error(
        (e as { message?: string })?.message ||
          (mode === 'optimize' ? 'AI 优化失败' : '重新生成失败'),
      );
    } finally {
      setRefiningCids(prev => {
        const next = new Set(prev);
        next.delete(cid);
        return next;
      });
    }
  };

  const importSelected = async () => {
    const picked = candidates.filter(c => c.selected);
    if (picked.length === 0) {
      toast.error('请至少选择一条候选');
      return;
    }
    const items: BulkImportItem[] = picked.map(c => ({
      input_payload: { user_input: c.user_input },
      expected_output: c.answer ? { answer: c.answer } : null,
      meta: { source: 'ai_generate' },
      note: c.note?.trim() || null,
      category: c.category ?? null,
    }));
    setImporting(true);
    try {
      const res = await datasetApi.bulkImport(datasetId, {
        items,
        pii_strategy: 'keep',
      });
      toast.success(`已导入 ${res.added} 条样本`);
      onDone();
      onClose();
    } catch (e) {
      toast.error((e as { message?: string })?.message || '导入失败');
    } finally {
      setImporting(false);
    }
  };

  return (
    <Modal open onOpenChange={o => !o && onClose()}>
      <ModalContent size="xl" preventClose={stage === 'streaming'}>
        <ModalHeader>
          <ModalTitle>
            <span className="inline-flex items-center gap-1.5">
              <Sparkles className="h-4 w-4 text-violet-500" /> AI 扩样
            </span>
          </ModalTitle>
        </ModalHeader>

        {stage === 'form' && (
          <FormStage
            task={task}
            count={count}
            onTaskChange={setTask}
            onCountChange={setCount}
          />
        )}

        {stage === 'streaming' && (
          <StreamingStage streamText={streamText} candidates={candidates} />
        )}

        {stage === 'review' && (
          <div className="flex-1 overflow-y-auto px-5 py-4">
            {candidates.length === 0 ? (
              <div className="py-10 text-center text-[12.5px] text-stone-400">
                没有生成候选，点下方「重新全部生成」再试一次。
              </div>
            ) : (
              <>
                <div className="mb-3 flex items-center gap-3">
                  <label className="inline-flex items-center gap-1.5 text-[12px] text-stone-600">
                    <input
                      type="checkbox"
                      aria-label="全选候选"
                      checked={allSelected}
                      onChange={toggleAll}
                      className="h-3.5 w-3.5 accent-primary-600"
                    />
                    全选
                  </label>
                  <span className="text-[11.5px] text-stone-400">
                    已选 {selectedCount} / {candidates.length}
                  </span>
                </div>
                <div className="space-y-2.5">
                  {candidates.map((c, i) => (
                    <AiGenCandidateCard
                      key={c.cid}
                      candidate={c}
                      index={i}
                      categories={categories}
                      refining={refiningCids.has(c.cid)}
                      onToggle={toggleOne}
                      onChangeInput={changeInput}
                      onChangeAnswer={changeAnswer}
                      onChangeNote={changeNote}
                      onOptimize={cid => void refine(cid, 'optimize')}
                      onRegenerate={cid => void refine(cid, 'regenerate')}
                      onRemove={removeOne}
                    />
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        <ModalFooter>
          {stage === 'form' && (
            <>
              <Button variant="ghost" size="sm" onClick={onClose}>
                取消
              </Button>
              <Button size="sm" onClick={() => void startStream()}>
                <Sparkles className="mr-1 h-3.5 w-3.5" /> 生成
              </Button>
            </>
          )}
          {stage === 'streaming' && (
            <>
              <NeonLoader
                size="sm"
                className="mr-auto"
                label={`AI 正在生成…已产出 ${candidates.length} 条候选`}
              />
              <Button variant="danger-outline" size="sm" onClick={stopStream}>
                <Square className="mr-1 h-3.5 w-3.5" /> 停止
              </Button>
            </>
          )}
          {stage === 'review' && (
            <>
              <Button
                variant="secondary"
                size="sm"
                className="mr-auto"
                onClick={regenerateAll}
              >
                <Sparkles className="mr-1 h-3.5 w-3.5" /> 重新全部生成
              </Button>
              <Button variant="ghost" size="sm" onClick={onClose}>
                取消
              </Button>
              <Button
                size="sm"
                loading={importing}
                disabled={selectedCount === 0}
                onClick={() => void importSelected()}
              >
                导入选中（{selectedCount}）
              </Button>
            </>
          )}
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

interface FormStageProps {
  task: string;
  count: number;
  onTaskChange: (v: string) => void;
  onCountChange: (v: number) => void;
}

const FormStage = ({ task, count, onTaskChange, onCountChange }: FormStageProps) => (
  <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4 text-[12.5px]">
    <p className="text-[11px] leading-snug text-stone-400">
      以本数据集现有样本为风格参照，让 AI 仿照流式生成新候选（走评测渠道，成本计入
      Trace）。生成后可挑拣 / 编辑 / 优化，再导入选中。
    </p>
    <div>
      <label className="mb-1 block text-[11.5px] text-stone-600">生成任务描述</label>
      <Textarea
        value={task}
        onChange={e => onTaskChange(e.target.value)}
        rows={3}
        placeholder="如：生成 Python 进阶知识点的问答样本，覆盖装饰器、生成器、异步等主题"
        className="text-[12px]"
      />
    </div>
    <div>
      <label className="mb-1 block text-[11.5px] text-stone-600">生成数量</label>
      <input
        type="number"
        min={1}
        max={50}
        value={count}
        onChange={e =>
          onCountChange(Math.max(1, Math.min(50, Number(e.target.value) || 1)))
        }
        className="w-24 rounded-md border border-stone-200 px-2 py-1.5 text-[12.5px]"
      />
      <span className="ml-2 text-[10.5px] text-stone-400">1–50 条</span>
    </div>
  </div>
);

interface StreamingStageProps {
  streamText: string;
  candidates: AiGenCandidate[];
}

const StreamingStage = ({ streamText, candidates }: StreamingStageProps) => (
  <div className="flex-1 overflow-y-auto px-5 py-4">
    <div className="grid grid-cols-2 gap-4">
      <div>
        <div className="mb-1.5 text-[11px] font-medium text-stone-500">AI 原文</div>
        <div className="h-[360px] overflow-y-auto rounded-lg border border-stone-200 bg-stone-50 p-3 text-[12px] leading-relaxed text-stone-700">
          <pre className="whitespace-pre-wrap break-words font-mono text-[11.5px]">
            {streamText}
            <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-primary-400 align-middle" />
          </pre>
        </div>
      </div>
      <div>
        <div className="mb-1.5 text-[11px] font-medium text-stone-500">
          候选（{candidates.length}）
        </div>
        <div className="h-[360px] space-y-2 overflow-y-auto rounded-lg border border-stone-200 bg-white p-2">
          {candidates.length === 0 ? (
            <div className="pt-8 text-center text-[11.5px] text-stone-300">
              解析完成后逐条浮现…
            </div>
          ) : (
            candidates.map((c, i) => (
              <div
                key={c.cid}
                className={cn(
                  'rounded-md border border-stone-200 bg-stone-50/60 p-2 text-[11.5px]',
                  'animate-in fade-in',
                )}
              >
                <div className="mb-0.5 text-[10px] font-medium text-stone-400">
                  候选 #{i + 1}
                </div>
                <div className="line-clamp-2 text-stone-700">{c.user_input}</div>
                <div className="mt-1 line-clamp-2 text-stone-500">{c.answer}</div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  </div>
);

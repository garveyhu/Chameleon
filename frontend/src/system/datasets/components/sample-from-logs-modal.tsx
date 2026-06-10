/** 从调用日志采样 —— 两段式：筛选 → 候选评审（挑选/编辑/AI 优化）→ 导入选中。
 *
 *  与 AI 扩样一致：采样不再点确认就直接入库，先返回候选评审，挑选/二次编辑/AI 智能修改后
 *  再走 bulk-import 正式落库。候选脱敏在后端 preview 完成，前端只编辑纯文本。 */

import { useMutation } from '@tanstack/react-query';
import { HelpCircle, Loader2, Search, Sparkles } from 'lucide-react';
import { useMemo, useRef, useState } from 'react';

import { AgentPicker } from '@/core/components/common/agent-picker';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import {
  Modal,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { Tooltip } from '@/core/components/ui/tooltip';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { AiGenCandidateCard } from '@/system/datasets/components/ai-gen-candidate-card';
import { datasetApi } from '@/system/datasets/services/dataset';
import type {
  AiGenCandidate,
  PiiStrategy,
  SampleCandidate,
} from '@/system/datasets/types/dataset';

interface Props {
  datasetId: EntityId;
  onClose: () => void;
  /** 导入落库已生效，让父页刷新样本列表与角标。 */
  onDone: () => void;
}

/** 评审态单条：候选卡片字段 + 采样来源元信息（导入时回带）。 */
type ReviewItem = AiGenCandidate & { meta: Record<string, unknown> };

const SAMPLE_REFINE_TASK =
  '这是从真实调用日志采样的评测样本，请在不改变原意的前提下，让「问题」更清晰、' +
  '「理想回答」更准确完整，输出 JSON {"user_input":"...","answer":"..."}。';

const PII_OPTIONS: { value: PiiStrategy; label: string; hint: string }[] = [
  { value: 'mask', label: '打码', hint: '把邮箱 / 手机号 / 身份证等替换为占位符后保留（默认）' },
  { value: 'drop', label: '丢弃', hint: '含敏感信息的整条样本直接跳过，不入库' },
  { value: 'keep', label: '保留', hint: '原样保留，仅在明确无敏感信息时使用' },
];

const PII_TOOLTIP =
  '敏感信息（PII）指邮箱、手机号、身份证号等可识别到个人的信息。采样会按所选策略处理，避免把真实个人信息带入评测集。';

export const SampleFromLogsModal = ({ datasetId, onClose, onDone }: Props) => {
  const [stage, setStage] = useState<'form' | 'review'>('form');
  const [agentKey, setAgentKey] = useState('');
  const [appId, setAppId] = useState('');
  const [limit, setLimit] = useState(50);
  const [piiStrategy, setPiiStrategy] = useState<PiiStrategy>('mask');
  const [includeExpected, setIncludeExpected] = useState(true);
  const [successOnly, setSuccessOnly] = useState(true);

  const [candidates, setCandidates] = useState<ReviewItem[]>([]);
  const [skipped, setSkipped] = useState(0);
  const [droppedPii, setDroppedPii] = useState(0);
  const [refiningCid, setRefiningCid] = useState<string | null>(null);
  const cidCounter = useRef(0);

  const selectedCount = useMemo(() => candidates.filter(c => c.selected).length, [candidates]);
  const allSelected = candidates.length > 0 && selectedCount === candidates.length;

  const toReq = () => ({
    agent_key: agentKey.trim() || undefined,
    app_id: appId.trim() || undefined,
    limit,
    pii_strategy: piiStrategy,
    include_response_as_expected: includeExpected,
    success: successOnly ? true : undefined,
  });

  const previewMut = useMutation({
    mutationFn: () => datasetApi.previewSampleFromLogs(datasetId, toReq()),
    onSuccess: data => {
      const items: ReviewItem[] = data.candidates.map((c: SampleCandidate) => ({
        cid: `s${cidCounter.current++}`,
        user_input: c.user_input,
        answer: c.answer ?? '',
        selected: true,
        meta: { ...c.meta, source: 'log_sample' },
      }));
      setCandidates(items);
      setSkipped(data.skipped);
      setDroppedPii(data.dropped_pii);
      setStage('review');
      if (items.length === 0) {
        toast.info('没有符合条件的新日志可采样（可能都已采过或被脱敏丢弃）');
      }
    },
    onError: e => toast.error('采样预览失败：' + (e as Error).message),
  });

  const importMut = useMutation({
    mutationFn: () => {
      const picked = candidates.filter(c => c.selected);
      return datasetApi.bulkImport(datasetId, {
        items: picked.map(c => ({
          input_payload: { user_input: c.user_input },
          expected_output: c.answer.trim() ? { answer: c.answer } : null,
          meta: c.meta,
        })),
        pii_strategy: 'keep', // 后端 preview 已脱敏，导入阶段不再二次处理
      });
    },
    onSuccess: data => {
      toast.success(`已导入 ${data.added} 条样本`);
      onDone();
      onClose();
    },
    onError: e => toast.error('导入失败：' + (e as Error).message),
  });

  const patch = (cid: string, p: Partial<ReviewItem>) =>
    setCandidates(prev => prev.map(c => (c.cid === cid ? { ...c, ...p } : c)));

  const optimize = async (cid: string) => {
    const c = candidates.find(x => x.cid === cid);
    if (!c) return;
    setRefiningCid(cid);
    try {
      const r = await datasetApi.refineCandidate(datasetId, {
        task_description: SAMPLE_REFINE_TASK,
        candidate: { user_input: c.user_input, answer: c.answer },
        mode: 'optimize',
      });
      patch(cid, { user_input: r.user_input, answer: r.answer ?? '' });
    } catch (e) {
      toast.error('AI 优化失败：' + (e as Error).message);
    } finally {
      setRefiningCid(null);
    }
  };

  const activePii = PII_OPTIONS.find(o => o.value === piiStrategy);

  return (
    <Modal open onOpenChange={open => !open && onClose()}>
      <ModalContent size="xl">
        <ModalHeader>
          <ModalTitle>从调用日志采样</ModalTitle>
        </ModalHeader>

        {stage === 'form' ? (
          <>
            <div className="space-y-3 px-4 py-3 text-[12.5px]">
              <p className="text-[11px] leading-snug text-stone-500">
                从历史调用日志里抽取真实请求 / 返回整理成候选样本。采样后先进入评审，挑选 /
                二次编辑 / AI 智能修改后再导入，不会直接入库。
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-[11.5px] text-stone-600">智能体</label>
                  <AgentPicker value={agentKey} onChange={setAgentKey} width={232} />
                  <p className="mt-1 text-[10.5px] leading-tight text-stone-400">
                    选「全部应用」= 不限智能体
                  </p>
                </div>
                <div>
                  <label className="mb-1 block text-[11.5px] text-stone-600">
                    应用 / 调用方（可选）
                  </label>
                  <Input
                    value={appId}
                    onChange={e => setAppId(e.target.value)}
                    placeholder="留空 = 所有调用方"
                    className="font-mono text-[12px]"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-[11.5px] text-stone-600">
                    采样上限（1-500）
                  </label>
                  <Input
                    type="number"
                    min={1}
                    max={500}
                    value={limit}
                    onChange={e =>
                      setLimit(Math.max(1, Math.min(500, Number(e.target.value) || 50)))
                    }
                    className="text-[12px]"
                  />
                </div>
                <div>
                  <label className="mb-1 flex items-center gap-1 text-[11.5px] text-stone-600">
                    敏感信息脱敏（PII）
                    <Tooltip content={PII_TOOLTIP}>
                      <HelpCircle className="h-3.5 w-3.5 cursor-help text-stone-400" />
                    </Tooltip>
                  </label>
                  <div className="flex gap-1">
                    {PII_OPTIONS.map(opt => (
                      <Tooltip key={opt.value} content={opt.hint}>
                        <button
                          type="button"
                          onClick={() => setPiiStrategy(opt.value)}
                          className={cn(
                            'flex-1 rounded-md border px-2 py-1 text-[11.5px] transition',
                            piiStrategy === opt.value
                              ? 'border-amber-300 bg-amber-50 text-amber-700'
                              : 'border-stone-200 bg-white text-stone-600 hover:bg-stone-50',
                          )}
                        >
                          {opt.label}
                        </button>
                      </Tooltip>
                    ))}
                  </div>
                  {activePii ? (
                    <p className="mt-1 text-[10.5px] leading-tight text-stone-400">
                      {activePii.hint}
                    </p>
                  ) : null}
                </div>
              </div>
              <div className="flex gap-4 pt-1">
                <label className="flex items-center gap-2 text-[11.5px] text-stone-600">
                  <input
                    type="checkbox"
                    checked={successOnly}
                    onChange={e => setSuccessOnly(e.target.checked)}
                  />
                  仅采样成功的调用
                </label>
                <label className="flex items-center gap-2 text-[11.5px] text-stone-600">
                  <input
                    type="checkbox"
                    checked={includeExpected}
                    onChange={e => setIncludeExpected(e.target.checked)}
                  />
                  用「调用返回」作为「预期输出」
                </label>
              </div>
            </div>
            <ModalFooter>
              <Button variant="ghost" size="sm" onClick={onClose}>
                取消
              </Button>
              <Button
                size="sm"
                disabled={previewMut.isPending}
                onClick={() => previewMut.mutate()}
              >
                {previewMut.isPending ? (
                  <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Search className="mr-1 h-3.5 w-3.5" />
                )}
                采样预览
              </Button>
            </ModalFooter>
          </>
        ) : (
          <>
            <div className="flex items-center gap-2 border-b border-stone-100 px-4 py-2 text-[11.5px]">
              <label className="flex items-center gap-1.5 text-stone-600">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={e =>
                    setCandidates(prev =>
                      prev.map(c => ({ ...c, selected: e.target.checked })),
                    )
                  }
                  className="h-3.5 w-3.5 accent-primary-600"
                />
                全选
              </label>
              <span className="text-stone-400">
                已选 {selectedCount} / {candidates.length}
              </span>
              {(skipped > 0 || droppedPii > 0) && (
                <span className="text-stone-400">
                  · 已采过跳过 {skipped} · 敏感丢弃 {droppedPii}
                </span>
              )}
              <Button
                variant="ghost"
                size="sm"
                className="ml-auto"
                onClick={() => setStage('form')}
              >
                重新采样
              </Button>
            </div>
            <div className="max-h-[60vh] space-y-2 overflow-y-auto px-4 py-3">
              {candidates.length === 0 ? (
                <p className="py-10 text-center text-[12px] text-stone-400">
                  没有可采样的候选。调整筛选条件后「重新采样」。
                </p>
              ) : (
                candidates.map((c, i) => (
                  <AiGenCandidateCard
                    key={c.cid}
                    candidate={c}
                    index={i}
                    refining={refiningCid === c.cid}
                    showRegenerate={false}
                    onToggle={cid => patch(cid, { selected: !c.selected })}
                    onChangeInput={(cid, v) => patch(cid, { user_input: v })}
                    onChangeAnswer={(cid, v) => patch(cid, { answer: v })}
                    onChangeNote={(cid, v) => patch(cid, { note: v })}
                    onOptimize={optimize}
                    onRegenerate={() => undefined}
                    onRemove={cid => setCandidates(prev => prev.filter(x => x.cid !== cid))}
                  />
                ))
              )}
            </div>
            <ModalFooter className="flex items-center">
              <span className="mr-auto inline-flex items-center gap-1 text-[10.5px] text-stone-400">
                <Sparkles className="h-3 w-3" /> 点候选卡上的「AI 优化」可二次智能修改
              </span>
              <Button variant="ghost" size="sm" onClick={onClose}>
                取消
              </Button>
              <Button
                size="sm"
                disabled={selectedCount === 0 || importMut.isPending}
                onClick={() => importMut.mutate()}
              >
                {importMut.isPending && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
                导入选中（{selectedCount}）
              </Button>
            </ModalFooter>
          </>
        )}
      </ModalContent>
    </Modal>
  );
};

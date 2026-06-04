/** 手动发起运行 Modal —— 运行名称 + judge + 评分配置 + 被测对象（模型 / 智能体二选一）。
 *
 * 复杂度集中三块：
 *  1) judge 下拉拉 /judges，按 judge 条件渲染评分配置区（criteria / reference / upcoming）
 *  2) 被测对象互斥：model_override（ModelPicker）或 agent_key（AgentPicker）二选一
 *  3) 提交走同步端点 datasetApi.run（跑完才返回，loading 期间禁用 + spinner + 文案）
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { useState } from 'react';

import { AgentPicker } from '@/core/components/common/agent-picker';
import { ModelPicker } from '@/core/components/common/model-picker';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { JudgeConfigFields } from '@/system/datasets/components/judge-config-fields';
import { datasetApi } from '@/system/datasets/services/dataset';
import type {
  CreateDatasetRunRequest,
  DatasetRunDetail,
} from '@/system/datasets/types/dataset';
import {
  buildJudgeConfig,
  JUDGE_META,
  judgeConfigKind,
} from '@/system/datasets/utils/judge-meta';

type TargetKind = 'model' | 'agent';

interface RunStartModalProps {
  datasetId: EntityId;
  /** judge 列表（来自 detail page 的 /judges query；空则退回内置默认） */
  judges?: string[];
  onClose: () => void;
  /** 成功后回调 —— 传回新 run，供调用方刷新列表 + 展示详情 */
  onStarted: (run: DatasetRunDetail) => void;
}

const defaultRunName = (): string => {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `手动运行 ${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(
    now.getHours(),
  )}:${pad(now.getMinutes())}`;
};

export const RunStartModal = ({
  datasetId,
  judges,
  onClose,
  onStarted,
}: RunStartModalProps) => {
  const qc = useQueryClient();
  const [name, setName] = useState(() => defaultRunName());
  const [judge, setJudge] = useState('exact_match');
  const [criteria, setCriteria] = useState('');
  const [targetKind, setTargetKind] = useState<TargetKind>('model');
  const [modelOverride, setModelOverride] = useState('');
  const [agentKey, setAgentKey] = useState('');

  const runMut = useMutation({
    mutationFn: (req: CreateDatasetRunRequest) =>
      datasetApi.run(datasetId, req),
    onSuccess: run => {
      toast.success('评测已完成');
      qc.invalidateQueries({ queryKey: ['datasets', String(datasetId), 'runs'] });
      onStarted(run);
      onClose();
    },
    onError: (e: unknown) =>
      toast.error((e as { message?: string })?.message || '运行失败'),
  });

  const judgeOptions = judges?.length ? judges : ['exact_match'];
  const isUpcoming = judgeConfigKind(judge) === 'upcoming';
  const canSubmit =
    !!name.trim() && !isUpcoming && !runMut.isPending;

  const handleSubmit = () => {
    if (!canSubmit) return;
    const req: CreateDatasetRunRequest = {
      name: name.trim(),
      judge,
      judge_config: buildJudgeConfig(judge, criteria),
      model_override: targetKind === 'model' ? modelOverride || undefined : undefined,
      agent_key: targetKind === 'agent' ? agentKey || undefined : undefined,
    };
    runMut.mutate(req);
  };

  return (
    <Modal open onOpenChange={o => !o && !runMut.isPending && onClose()}>
      <ModalContent size="md" preventClose={runMut.isPending}>
        <ModalHeader>
          <ModalTitle>新建运行</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div className="space-y-1.5">
            <Label>
              运行名称 <span className="text-rose-500">*</span>
            </Label>
            <Input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="给本次运行起个名"
              maxLength={128}
            />
          </div>

          <div className="space-y-1.5">
            <Label>评分方式</Label>
            <Select value={judge} onValueChange={setJudge}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {judgeOptions.map(j => (
                  <SelectItem key={j} value={j}>
                    {JUDGE_META[j]?.label ?? j}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {JUDGE_META[judge] && (
              <p className="text-[10.5px] leading-snug text-stone-400">
                {JUDGE_META[judge].desc}
              </p>
            )}
          </div>

          <JudgeConfigFields
            judge={judge}
            criteria={criteria}
            onCriteriaChange={setCriteria}
          />

          <div className="space-y-2">
            <Label>被测对象</Label>
            <div className="inline-flex gap-1 rounded-lg border border-stone-200 bg-white p-0.5">
              {(
                [
                  ['model', '指定模型'],
                  ['agent', '指定智能体'],
                ] as const
              ).map(([k, label]) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setTargetKind(k)}
                  className={cn(
                    'rounded-md px-3 py-1 text-[12px] transition',
                    targetKind === k
                      ? 'bg-stone-800 text-white'
                      : 'text-stone-600 hover:bg-stone-100',
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            <div>
              {targetKind === 'model' ? (
                <ModelPicker
                  value={modelOverride}
                  onChange={setModelOverride}
                  placeholder="不指定 · 用数据集默认模型"
                  width={280}
                />
              ) : (
                <AgentPicker
                  value={agentKey}
                  onChange={setAgentKey}
                  width={280}
                />
              )}
            </div>
            <p className="text-[10.5px] leading-snug text-stone-400">
              {targetKind === 'model'
                ? '直接用所选模型逐条跑数据集样本'
                : '用所选智能体（含其 Prompt / 工具 / 知识库）跑评测'}
            </p>
          </div>

          {runMut.isPending && (
            <div className="flex items-center gap-2 rounded-md border border-blue-100 bg-blue-50/60 px-3 py-2 text-[11.5px] text-blue-700">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              评测进行中，可能需要数十秒，请勿关闭…
            </div>
          )}
        </ModalBody>
        <ModalFooter>
          <Button
            variant="ghost"
            onClick={onClose}
            disabled={runMut.isPending}
          >
            取消
          </Button>
          <Button variant="primary" disabled={!canSubmit} onClick={handleSubmit}>
            {runMut.isPending ? '评测中…' : '开始运行'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

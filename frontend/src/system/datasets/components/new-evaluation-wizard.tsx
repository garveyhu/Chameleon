/** 新建评估统一入口（方案C）—— 选数据集 → 评分方案 → 立即跑 / 定时。
 *
 * 让「评估」成为单一心智入口：两种执行分流到现有端点
 *  - 立即跑 → datasetApi.run（同步，跑完才返回，可能数十秒）
 *  - 定时   → evalJobApi.create（带 cron + 可选 alert，落 EvalJob）
 * 两条都引用同一 ScoringScheme（模板 or 自定义 judge）。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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
import { get } from '@/core/lib/request';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import type { EntityId, PageResult } from '@/core/types/api';
import { ScoringSchemePicker } from '@/system/datasets/components/scoring-scheme-picker';
import { datasetApi } from '@/system/datasets/services/dataset';
import type {
  CreateDatasetRunRequest,
  DatasetRunDetail,
} from '@/system/datasets/types/dataset';
import {
  defaultJudgeScheme,
  type ScoringScheme,
} from '@/system/datasets/types/scoring-scheme';
import { schemeToRunFields } from '@/system/datasets/utils/scoring-scheme-payload';
import { evalJobApi } from '@/system/eval_jobs/services/eval-job';
import type { CreateEvalJobPayload } from '@/system/eval_jobs/types/eval-job';
import {
  CRON_CUSTOM_SENTINEL,
  CRON_PRESETS,
} from '@/system/eval_jobs/types/eval-job';

interface DatasetOption {
  id: EntityId;
  name: string;
  item_count: number;
}

type RunMode = 'now' | 'scheduled';
type TargetKind = 'model' | 'agent';

interface NewEvaluationWizardProps {
  /** 在数据集上下文则预填并锁定数据集 */
  presetDatasetId?: EntityId;
  judges?: string[];
  onClose: () => void;
  /** 立即跑成功后回调（跳运行详情整页） */
  onRunStarted?: (datasetId: EntityId, run: DatasetRunDetail) => void;
  /** 定时任务创建成功后回调 */
  onJobCreated?: () => void;
}

const defaultRunName = (): string => {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `评估 ${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(
    now.getHours(),
  )}:${pad(now.getMinutes())}`;
};

export const NewEvaluationWizard = ({
  presetDatasetId,
  judges,
  onClose,
  onRunStarted,
  onJobCreated,
}: NewEvaluationWizardProps) => {
  const qc = useQueryClient();
  const lockDataset = presetDatasetId != null;
  const [datasetId, setDatasetId] = useState<string>(() =>
    presetDatasetId != null ? String(presetDatasetId) : '',
  );
  const [scheme, setScheme] = useState<ScoringScheme>(defaultJudgeScheme);
  const [runMode, setRunMode] = useState<RunMode>('now');
  const [name, setName] = useState(() => defaultRunName());
  const [targetKind, setTargetKind] = useState<TargetKind>('model');
  const [modelOverride, setModelOverride] = useState('');
  const [agentKey, setAgentKey] = useState('');
  // 归属 Key（雪花 id 以字符串存，'' = 不归属/内部评测）
  const [apiKeyId, setApiKeyId] = useState('');
  // 定时专属
  const [jobKey, setJobKey] = useState('');
  const [cronPreset, setCronPreset] = useState('0 9 * * *');
  const [cronCustom, setCronCustom] = useState('');

  const datasetsQ = useQuery({
    queryKey: ['new-eval:datasets'],
    queryFn: () =>
      get<PageResult<DatasetOption>>('/v1/admin/datasets', {
        params: { page_size: 200 },
      }),
    enabled: !lockDataset,
    staleTime: 30_000,
  });

  // 归属 Key 候选：评测本不经 Key，仅作 token/成本/trace 的归属盖章用
  const keysQ = useQuery({
    queryKey: ['new-eval:api-keys'],
    queryFn: () =>
      get<PageResult<{ id: EntityId; name: string; key_prefix: string }>>(
        '/v1/admin/api-keys',
        { params: { page_size: 100 } },
      ),
    staleTime: 30_000,
  });
  const keyOptions = keysQ.data?.items ?? [];

  const runMut = useMutation({
    mutationFn: (req: CreateDatasetRunRequest) =>
      datasetApi.run(datasetId as unknown as EntityId, req),
    onSuccess: run => {
      toast.success('评测已完成');
      qc.invalidateQueries({
        queryKey: ['datasets', datasetId, 'runs'],
      });
      onRunStarted?.(datasetId as unknown as EntityId, run);
      onClose();
    },
    onError: (e: unknown) =>
      toast.error((e as { message?: string })?.message || '运行失败'),
  });

  const jobMut = useMutation({
    mutationFn: (payload: CreateEvalJobPayload) => evalJobApi.create(payload),
    onSuccess: () => {
      toast.success('定时评估已创建');
      qc.invalidateQueries({ queryKey: ['eval-jobs'] });
      onJobCreated?.();
      onClose();
    },
    onError: (e: unknown) =>
      toast.error((e as { message?: string })?.message || '创建失败'),
  });

  const isCustomCron = cronPreset === CRON_CUSTOM_SENTINEL;
  const finalCron = isCustomCron ? cronCustom.trim() : cronPreset;
  const schemeReady =
    scheme.mode === 'template' ? scheme.templateId != null : true;
  const pending = runMut.isPending || jobMut.isPending;

  const canSubmit =
    !!datasetId &&
    !!name.trim() &&
    schemeReady &&
    (runMode === 'now' || (!!finalCron && !!jobKey.trim())) &&
    !pending;

  const handleSubmit = () => {
    if (!canSubmit) return;
    const schemeFields = schemeToRunFields(scheme);
    if (runMode === 'now') {
      const req: CreateDatasetRunRequest = {
        name: name.trim(),
        ...schemeFields,
        model_override:
          targetKind === 'model' ? modelOverride || undefined : undefined,
        agent_key: targetKind === 'agent' ? agentKey || undefined : undefined,
        api_key_id: apiKeyId || undefined,
      };
      runMut.mutate(req);
    } else {
      const payload: CreateEvalJobPayload = {
        job_key: jobKey.trim(),
        name: name.trim(),
        dataset_id: datasetId as unknown as EntityId,
        target_kind: 'agent',
        target_key: targetKind === 'agent' ? agentKey || null : null,
        model_override: targetKind === 'model' ? modelOverride || null : null,
        judge: schemeFields.judge,
        judge_config: schemeFields.judge_config ?? null,
        template_id:
          scheme.mode === 'template' ? (scheme.templateId ?? null) : null,
        cron_expr: finalCron,
      };
      jobMut.mutate(payload);
    }
  };

  return (
    <Modal open onOpenChange={o => !o && !pending && onClose()}>
      <ModalContent size="lg" preventClose={pending}>
        <ModalHeader>
          <ModalTitle>新建评估</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          {!lockDataset && (
            <div className="space-y-1.5">
              <Label>
                数据集 <span className="text-rose-500">*</span>
              </Label>
              <Select value={datasetId} onValueChange={setDatasetId}>
                <SelectTrigger>
                  <SelectValue placeholder="选择数据集…" />
                </SelectTrigger>
                <SelectContent>
                  {(datasetsQ.data?.items ?? []).map(d => (
                    <SelectItem key={String(d.id)} value={String(d.id)}>
                      {d.name}（{d.item_count} 样本）
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="space-y-1.5">
            <Label>
              评估名称 <span className="text-rose-500">*</span>
            </Label>
            <Input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="给本次评估起个名"
              maxLength={128}
            />
          </div>

          <ScoringSchemePicker value={scheme} onChange={setScheme} judges={judges} />

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
                  width={300}
                />
              ) : (
                <AgentPicker value={agentKey} onChange={setAgentKey} width={300} />
              )}
            </div>
          </div>

          {runMode === 'now' && (
            <div className="space-y-1.5">
              <Label>归属 Key（可选）</Label>
              <Select
                value={apiKeyId || 'none'}
                onValueChange={v => setApiKeyId(v === 'none' ? '' : v)}
              >
                <SelectTrigger className="w-[300px]">
                  <SelectValue placeholder="不归属 · 内部评测" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">不归属 · 内部评测</SelectItem>
                  {keyOptions.map(k => (
                    <SelectItem key={String(k.id)} value={String(k.id)}>
                      {k.name}
                      <span className="ml-1.5 font-mono text-[10px] text-stone-400">
                        {k.key_prefix}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[10.5px] leading-snug text-stone-400">
                评测本是内部流量、不经 Key。选一个后，本次评测的 token / 成本 / trace
                会计到该 Key 名下，Trace 列表的「Key / 来源」显示其名，便于按 Key
                单独统计评测花销。
              </p>
            </div>
          )}

          <div className="space-y-2">
            <Label>执行方式</Label>
            <div className="inline-flex gap-1 rounded-lg border border-stone-200 bg-white p-0.5">
              {(
                [
                  ['now', '立即跑一次'],
                  ['scheduled', '定时周期跑'],
                ] as const
              ).map(([k, label]) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setRunMode(k)}
                  className={cn(
                    'rounded-md px-3 py-1 text-[12px] transition',
                    runMode === k
                      ? 'bg-stone-800 text-white'
                      : 'text-stone-600 hover:bg-stone-100',
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            {runMode === 'scheduled' && (
              <div className="grid grid-cols-2 gap-3 pt-1">
                <div className="space-y-1.5">
                  <Label>
                    job_key <span className="text-rose-500">*</span>
                  </Label>
                  <Input
                    value={jobKey}
                    onChange={e => setJobKey(e.target.value)}
                    placeholder="daily-baseline"
                    className="font-mono"
                    maxLength={64}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>Cron 触发时间</Label>
                  <Select value={cronPreset} onValueChange={setCronPreset}>
                    <SelectTrigger>
                      <SelectValue placeholder="选预设…" />
                    </SelectTrigger>
                    <SelectContent>
                      {CRON_PRESETS.map(p => (
                        <SelectItem key={p.label} value={p.value}>
                          {p.label}
                          {p.value !== CRON_CUSTOM_SENTINEL && `（${p.value}）`}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {isCustomCron && (
                    <Input
                      value={cronCustom}
                      onChange={e => setCronCustom(e.target.value)}
                      placeholder="* * * * *（分 时 日 月 周）"
                      className="font-mono"
                    />
                  )}
                </div>
              </div>
            )}
          </div>

          {runMut.isPending && (
            <div className="flex items-center gap-2 rounded-md border border-blue-100 bg-blue-50/60 px-3 py-2 text-[11.5px] text-blue-700">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              评测进行中，可能需要数十秒，请勿关闭…
            </div>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            取消
          </Button>
          <Button variant="primary" disabled={!canSubmit} onClick={handleSubmit}>
            {pending
              ? runMode === 'now'
                ? '评测中…'
                : '创建中…'
              : runMode === 'now'
                ? '开始评估'
                : '创建定时评估'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

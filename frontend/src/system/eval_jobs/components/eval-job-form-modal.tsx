/** 定时任务 创建 / 编辑 Modal —— 数据集 + 评分方案 + 触发周期 + 被测对象 + 告警
 *
 * 设计要点：
 *  - 任务标识（job_key）自动生成，不让用户手填；编辑态只读展示。
 *  - 被测对象走 AgentPicker（含工作流类智能体），不手填 key。
 *  - 触发周期用 CronBuilder 可视化生成。
 *  - 启用状态用开关；评分方案选模板 or 自定义 judge（带中文说明）。
 */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { AgentPicker } from '@/core/components/common/agent-picker';
import { CronBuilder } from '@/core/components/common/cron-builder';
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
import { Switch } from '@/core/components/ui/switch';
import { get } from '@/core/lib/request';
import type { EntityId, PageResult } from '@/core/types/api';
import { ScoringSchemePicker } from '@/system/datasets/components/scoring-scheme-picker';
import type { ScoringScheme } from '@/system/datasets/types/scoring-scheme';
import { schemeToJobFields } from '@/system/datasets/utils/scoring-scheme-payload';
import type {
  AlertConfig,
  CreateEvalJobPayload,
  EvalJobItem,
  UpdateEvalJobPayload,
} from '@/system/eval_jobs/types/eval-job';

interface DatasetItem {
  id: EntityId;
  name: string;
  item_count: number;
}

interface EvalJobFormModalProps {
  open: boolean;
  /** 传入 = 编辑模式；不传 = 创建 */
  initial?: EvalJobItem | null;
  loading: boolean;
  /** 预设数据集（新建评估 wizard 注入时锁定，隐藏选择器） */
  presetDatasetId?: EntityId;
  onClose: () => void;
  onSubmit: (payload: CreateEvalJobPayload | UpdateEvalJobPayload) => void;
}

/** 从已存 job 回填 ScoringScheme：绑了模板 → template 模式；否则 judge 模式。 */
const initialScheme = (job?: EvalJobItem | null): ScoringScheme => {
  if (job?.template_id != null) {
    return { mode: 'template', templateId: job.template_id };
  }
  return {
    mode: 'judge',
    judge: job?.judge ?? 'exact_match',
    judgeConfig: job?.judge_config ?? undefined,
  };
};

/** 由显示名自动生成唯一任务标识：ASCII slug + 随机后缀，中文名退回 job-<rand>。 */
const genJobKey = (name: string): string => {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 24);
  const rand = Math.random().toString(36).slice(2, 8);
  return slug ? `${slug}-${rand}` : `job-${rand}`;
};

export const EvalJobFormModal = ({
  open,
  initial,
  loading,
  presetDatasetId,
  onClose,
  onSubmit,
}: EvalJobFormModalProps) => {
  const isEdit = !!initial;
  const [name, setName] = useState(() => initial?.name ?? '');
  const [description, setDescription] = useState(() => initial?.description ?? '');
  const [datasetId, setDatasetId] = useState<string>(() =>
    initial
      ? String(initial.dataset_id)
      : presetDatasetId != null
        ? String(presetDatasetId)
        : '',
  );
  const [targetKind] = useState<'agent' | 'graph'>(
    () => initial?.target_kind ?? 'agent',
  );
  const [targetKey, setTargetKey] = useState(() => initial?.target_key ?? '');
  const [modelOverride, setModelOverride] = useState(
    () => initial?.model_override ?? '',
  );
  const [promptOverride, setPromptOverride] = useState(
    () => initial?.prompt_override ?? '',
  );
  const [scheme, setScheme] = useState<ScoringScheme>(() => initialScheme(initial));
  const [cron, setCron] = useState(() => initial?.cron_expr ?? '0 9 * * *');
  const [enabled, setEnabled] = useState(() => initial?.enabled ?? true);
  const [alertEnabled, setAlertEnabled] = useState(() => !!initial?.alert_config);
  const [alertKind, setAlertKind] = useState<'slack' | 'webhook'>(
    () => initial?.alert_config?.kind ?? 'slack',
  );
  const [alertTarget, setAlertTarget] = useState(
    () => initial?.alert_config?.target ?? '',
  );
  const [alertThreshold, setAlertThreshold] = useState(() =>
    String(initial?.alert_config?.regression_threshold ?? 0.1),
  );
  const [alertSilence, setAlertSilence] = useState(() =>
    String(initial?.alert_config?.silence_minutes ?? 60),
  );

  const lockDataset = isEdit || presetDatasetId != null;
  const datasetsQ = useQuery({
    queryKey: ['eval-job-modal:datasets'],
    queryFn: () =>
      get<PageResult<DatasetItem>>('/v1/admin/datasets', {
        params: { page_size: 200 },
      }),
    enabled: open && !lockDataset,
    staleTime: 30_000,
  });

  const judgesQ = useQuery({
    queryKey: ['eval-job-modal:judges'],
    queryFn: () => get<string[]>('/v1/admin/datasets/judges'),
    enabled: open,
    staleTime: 30_000,
  });

  const schemeReady =
    scheme.mode === 'template' ? scheme.templateId != null : true;
  const canSubmit =
    !!cron.trim() &&
    !!datasetId &&
    schemeReady &&
    !!name.trim() &&
    !loading &&
    (!alertEnabled || !!alertTarget.trim());

  const buildAlert = (): AlertConfig | null => {
    if (!alertEnabled) return null;
    const threshold = parseFloat(alertThreshold);
    const silence = parseInt(alertSilence, 10);
    return {
      kind: alertKind,
      target: alertTarget.trim(),
      regression_threshold: Number.isFinite(threshold) ? threshold : 0.1,
      silence_minutes: Number.isFinite(silence) && silence > 0 ? silence : 60,
    };
  };

  const handleSubmit = () => {
    if (!canSubmit) return;
    const schemeFields = schemeToJobFields(scheme);
    if (isEdit) {
      const payload: UpdateEvalJobPayload = {
        name: name.trim(),
        description: description.trim() || null,
        target_kind: targetKind,
        target_key: targetKey.trim() || null,
        model_override: modelOverride.trim() || null,
        prompt_override: promptOverride.trim() || null,
        judge: schemeFields.judge,
        judge_config: schemeFields.judge_config,
        template_id: schemeFields.template_id,
        cron_expr: cron.trim(),
        alert_config: buildAlert(),
        enabled,
      };
      onSubmit(payload);
    } else {
      const payload: CreateEvalJobPayload = {
        job_key: genJobKey(name),
        name: name.trim(),
        description: description.trim() || null,
        dataset_id: datasetId as unknown as EntityId,
        target_kind: targetKind,
        target_key: targetKey.trim() || null,
        model_override: modelOverride.trim() || null,
        prompt_override: promptOverride.trim() || null,
        judge: schemeFields.judge,
        judge_config: schemeFields.judge_config,
        template_id:
          schemeFields.template_id === (0 as unknown as EntityId)
            ? null
            : schemeFields.template_id,
        cron_expr: cron.trim(),
        alert_config: buildAlert(),
        enabled,
      };
      onSubmit(payload);
    }
  };

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="lg">
        <ModalHeader>
          <ModalTitle>{isEdit ? '编辑定时任务' : '新建定时任务'}</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          {/* 任务名 + 启用开关 */}
          <div className="flex items-start gap-3">
            <div className="flex-1 space-y-1.5">
              <Label>
                任务名 <span className="text-rose-500">*</span>
              </Label>
              <Input
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="每日基线回归"
                maxLength={128}
              />
              {isEdit && initial && (
                <p className="text-[10.5px] text-stone-400">
                  任务标识 <span className="font-mono">{initial.job_key}</span> · 不可改
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label>启用</Label>
              <div className="flex h-[34px] items-center gap-2">
                <Switch checked={enabled} onCheckedChange={setEnabled} />
                <span className="text-[12px] text-stone-500">
                  {enabled ? '已启用' : '已停用'}
                </span>
              </div>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>描述</Label>
            <Input
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="可选"
              maxLength={500}
            />
          </div>

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
                    <SelectItem key={d.id} value={String(d.id)}>
                      {d.name}（{d.item_count} 条样本）
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <ScoringSchemePicker
            value={scheme}
            onChange={setScheme}
            judges={judgesQ.data}
          />

          <div className="space-y-1.5">
            <Label>触发周期</Label>
            <CronBuilder value={cron} onChange={setCron} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>被测对象</Label>
              <AgentPicker
                value={targetKey}
                onChange={setTargetKey}
                width={232}
              />
              <p className="text-[10.5px] leading-tight text-stone-400">
                不选则用数据集样本里记录的默认对象
              </p>
            </div>
            <div className="space-y-1.5">
              <Label>覆盖模型</Label>
              <ModelPicker
                value={modelOverride}
                onChange={setModelOverride}
                placeholder="不指定 · 用默认模型"
                width={232}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>系统提示词覆盖</Label>
            <textarea
              value={promptOverride}
              onChange={e => setPromptOverride(e.target.value)}
              placeholder="可选 · 用此提示词跑评测"
              rows={2}
              className="w-full rounded-md border border-stone-300/70 bg-white px-2.5 py-1.5 text-[12.5px] text-stone-800 outline-none transition focus:border-primary-500 focus:ring-1 focus:ring-primary-200"
            />
          </div>

          {/* 回归告警配置 */}
          <div className="rounded-md border border-stone-200/70 bg-stone-50/40 p-3 space-y-3">
            <label className="flex items-center gap-2 text-[12.5px] text-stone-800">
              <input
                type="checkbox"
                checked={alertEnabled}
                onChange={e => setAlertEnabled(e.target.checked)}
                className="h-3.5 w-3.5 accent-primary-500"
              />
              开启回归告警（分数明显下跌时通知）
            </label>
            {alertEnabled && (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label>通知渠道</Label>
                    <Select
                      value={alertKind}
                      onValueChange={v => setAlertKind(v as 'slack' | 'webhook')}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="slack">Slack</SelectItem>
                        <SelectItem value="webhook">Webhook（通用）</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>
                      通知地址 <span className="text-rose-500">*</span>
                    </Label>
                    <Input
                      value={alertTarget}
                      onChange={e => setAlertTarget(e.target.value)}
                      placeholder={
                        alertKind === 'slack'
                          ? 'https://hooks.slack.com/services/...'
                          : 'https://example.com/webhook'
                      }
                      className="font-mono text-[11.5px]"
                      maxLength={256}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label>分数跌幅阈值</Label>
                    <Input
                      type="number"
                      step={0.01}
                      value={alertThreshold}
                      onChange={e => setAlertThreshold(e.target.value)}
                      min={0}
                      max={1}
                    />
                    <div className="text-[10.5px] text-stone-400">
                      跌幅 ≥ 此值才发；典型 0.1 = 跌 10 个百分点
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <Label>静默期（分钟）</Label>
                    <Input
                      type="number"
                      step={1}
                      value={alertSilence}
                      onChange={e => setAlertSilence(e.target.value)}
                      min={1}
                    />
                    <div className="text-[10.5px] text-stone-400">
                      同一任务内不重复发；默认 60 分钟
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button variant="primary" disabled={!canSubmit} onClick={handleSubmit}>
            {loading ? '保存中…' : isEdit ? '保存' : '创建'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

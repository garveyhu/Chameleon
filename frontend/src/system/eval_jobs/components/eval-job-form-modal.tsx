/** EvalJob 创建 / 编辑 Modal —— cron preset + alert 配置
 *
 * 复杂度集中三块：
 *  1) cron preset 切换（自定义 mode 时露出 raw 输入）
 *  2) alert_config 启用切换：关 → null；开 → {kind, target, threshold, silence}
 *  3) dataset 下拉 / judge 下拉 用 useQuery 拉 admin 接口
 */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { ModelPicker } from '@/core/components/common/model-picker';
import { get } from '@/core/lib/request';
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
import type { EntityId, PageResult } from '@/core/types/api';
import { JudgeConfigFields } from '@/system/datasets/components/judge-config-fields';
import {
  buildJudgeConfig,
  JUDGE_META,
  readCriteria,
} from '@/system/datasets/utils/judge-meta';
import type {
  AlertConfig,
  CreateEvalJobPayload,
  EvalJobItem,
  UpdateEvalJobPayload,
} from '@/system/eval_jobs/types/eval-job';
import {
  CRON_CUSTOM_SENTINEL,
  CRON_PRESETS,
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
  onClose: () => void;
  onSubmit: (
    payload: CreateEvalJobPayload | UpdateEvalJobPayload,
  ) => void;
}

export const EvalJobFormModal = ({
  open,
  initial,
  loading,
  onClose,
  onSubmit,
}: EvalJobFormModalProps) => {
  const isEdit = !!initial;
  // 惰性初始化 + 父层 remount key（react-hooks/set-state-in-effect 禁副作用同步）
  const [jobKey, setJobKey] = useState(() => initial?.job_key ?? '');
  const [name, setName] = useState(() => initial?.name ?? '');
  const [description, setDescription] = useState(
    () => initial?.description ?? '',
  );
  const [datasetId, setDatasetId] = useState<string>(() =>
    initial ? String(initial.dataset_id) : '',
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
  const [judge, setJudge] = useState(() => initial?.judge ?? 'exact_match');
  const [criteria, setCriteria] = useState(() =>
    readCriteria(initial?.judge_config),
  );
  const [cronPreset, setCronPreset] = useState(() => {
    if (!initial) return '0 9 * * *';
    const preset = CRON_PRESETS.find(
      p => p.value === initial.cron_expr && p.value !== CRON_CUSTOM_SENTINEL,
    );
    return preset ? initial.cron_expr : CRON_CUSTOM_SENTINEL;
  });
  const [cronCustom, setCronCustom] = useState(() => {
    if (!initial) return '';
    const preset = CRON_PRESETS.find(
      p => p.value === initial.cron_expr && p.value !== CRON_CUSTOM_SENTINEL,
    );
    return preset ? '' : initial.cron_expr;
  });
  const [alertEnabled, setAlertEnabled] = useState(
    () => !!initial?.alert_config,
  );
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

  const datasetsQ = useQuery({
    queryKey: ['eval-job-modal:datasets'],
    queryFn: () =>
      get<PageResult<DatasetItem>>('/v1/admin/datasets', {
        params: { page_size: 200 },
      }),
    enabled: open,
    staleTime: 30_000,
  });

  const judgesQ = useQuery({
    queryKey: ['eval-job-modal:judges'],
    queryFn: () => get<string[]>('/v1/admin/datasets/judges'),
    enabled: open,
    staleTime: 30_000,
  });

  const isCustomCron = cronPreset === CRON_CUSTOM_SENTINEL;
  const finalCron = isCustomCron ? cronCustom.trim() : cronPreset;
  const canSubmit =
    !!finalCron &&
    !!datasetId &&
    (isEdit || !!jobKey.trim()) &&
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
    const judgeConfig = buildJudgeConfig(judge, criteria) ?? null;
    if (isEdit) {
      const payload: UpdateEvalJobPayload = {
        name: name.trim(),
        description: description.trim() || null,
        target_kind: targetKind,
        target_key: targetKey.trim() || null,
        model_override: modelOverride.trim() || null,
        prompt_override: promptOverride.trim() || null,
        judge,
        judge_config: judgeConfig,
        cron_expr: finalCron,
        alert_config: buildAlert(),
      };
      onSubmit(payload);
    } else {
      const payload: CreateEvalJobPayload = {
        job_key: jobKey.trim(),
        name: name.trim(),
        description: description.trim() || null,
        dataset_id: datasetId as unknown as EntityId,
        target_kind: targetKind,
        target_key: targetKey.trim() || null,
        model_override: modelOverride.trim() || null,
        prompt_override: promptOverride.trim() || null,
        judge,
        judge_config: judgeConfig,
        cron_expr: finalCron,
        alert_config: buildAlert(),
      };
      onSubmit(payload);
    }
  };

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="lg">
        <ModalHeader>
          <ModalTitle>{isEdit ? '编辑评测任务' : '新建评测任务'}</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>
                job_key <span className="text-rose-500">*</span>
                <span className="ml-1 text-[11px] text-stone-400">
                  · 唯一；a-zA-Z0-9_-:.
                </span>
              </Label>
              <Input
                value={jobKey}
                onChange={e => setJobKey(e.target.value)}
                placeholder="daily-baseline"
                className="font-mono"
                disabled={isEdit}
                maxLength={64}
              />
            </div>
            <div className="space-y-1.5">
              <Label>
                显示名 <span className="text-rose-500">*</span>
              </Label>
              <Input
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="每日基线回归"
                maxLength={128}
              />
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

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>
                Dataset <span className="text-rose-500">*</span>
              </Label>
              <Select
                value={datasetId}
                onValueChange={setDatasetId}
                disabled={isEdit}
              >
                <SelectTrigger>
                  <SelectValue placeholder="选择数据集…" />
                </SelectTrigger>
                <SelectContent>
                  {(datasetsQ.data?.items ?? []).map(d => (
                    <SelectItem key={d.id} value={String(d.id)}>
                      {d.name}（{d.item_count} items）
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>评分方式</Label>
              <Select value={judge} onValueChange={setJudge}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(judgesQ.data ?? ['exact_match']).map(j => (
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
          </div>

          <JudgeConfigFields
            judge={judge}
            criteria={criteria}
            onCriteriaChange={setCriteria}
          />

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
            <div className="text-[10.5px] text-stone-400">
              当前表达式：
              <span className="font-mono text-stone-600">
                {finalCron || '—'}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>覆盖模型</Label>
              <ModelPicker
                value={modelOverride}
                onChange={setModelOverride}
                placeholder="不指定 · 用默认模型"
                width={232}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Target key</Label>
              <Input
                value={targetKey}
                onChange={e => setTargetKey(e.target.value)}
                placeholder="可选 · agent_key / graph_key"
                maxLength={64}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>System prompt override</Label>
            <textarea
              value={promptOverride}
              onChange={e => setPromptOverride(e.target.value)}
              placeholder="可选 · 用此 prompt 跑评测"
              rows={2}
              className="w-full rounded-md border border-stone-300/70 bg-white px-2.5 py-1.5 text-[12.5px] text-stone-800 outline-none transition focus:border-primary-500 focus:ring-1 focus:ring-primary-200"
            />
          </div>

          {/* Alert 配置 */}
          <div className="rounded-md border border-stone-200/70 bg-stone-50/40 p-3 space-y-3">
            <label className="flex items-center gap-2 text-[12.5px] text-stone-800">
              <input
                type="checkbox"
                checked={alertEnabled}
                onChange={e => setAlertEnabled(e.target.checked)}
                className="h-3.5 w-3.5 accent-primary-500"
              />
              开启 regression 告警
            </label>
            {alertEnabled && (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label>渠道</Label>
                    <Select
                      value={alertKind}
                      onValueChange={v =>
                        setAlertKind(v as 'slack' | 'webhook')
                      }
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
                      Target URL <span className="text-rose-500">*</span>
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
                      同 (job, kind) 内不重复发；默认 60 min
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
          <Button
            variant="primary"
            disabled={!canSubmit}
            onClick={handleSubmit}
          >
            {loading ? '保存中…' : isEdit ? '保存' : '创建'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

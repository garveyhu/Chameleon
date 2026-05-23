import type { EntityId } from '@/core/types/api';

export interface AlertConfig {
  kind: 'slack' | 'webhook';
  target: string;
  regression_threshold?: number;
  silence_minutes?: number;
}

export interface EvalJobItem {
  id: EntityId;
  job_key: string;
  name: string;
  description: string | null;
  dataset_id: EntityId;
  target_kind: 'agent' | 'graph';
  target_key: string | null;
  model_override: string | null;
  prompt_override: string | null;
  judge: string;
  cron_expr: string;
  alert_config: AlertConfig | null;
  enabled: boolean;
  last_run_at: string | null;
  last_score: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateEvalJobPayload {
  job_key: string;
  name: string;
  description?: string | null;
  dataset_id: EntityId;
  target_kind?: 'agent' | 'graph';
  target_key?: string | null;
  model_override?: string | null;
  prompt_override?: string | null;
  judge?: string;
  cron_expr: string;
  alert_config?: AlertConfig | null;
  enabled?: boolean;
}

export interface UpdateEvalJobPayload {
  name?: string;
  description?: string | null;
  target_kind?: 'agent' | 'graph';
  target_key?: string | null;
  model_override?: string | null;
  prompt_override?: string | null;
  judge?: string;
  cron_expr?: string;
  alert_config?: AlertConfig | null;
  enabled?: boolean;
}

export interface EvalJobRunItem {
  id: EntityId;
  job_id: EntityId;
  dataset_run_id: EntityId | null;
  triggered_by: 'cron' | 'manual' | 'api' | string;
  status: 'pending' | 'running' | 'success' | 'failed' | 'cancelled' | string;
  mean_score: string | null;
  delta_score: string | null;
  alert_sent: boolean;
  alert_target: string | null;
  error: { type: string; message: string } | null;
  created_at: string;
  finished_at: string | null;
}

export interface TriggerEvalJobResult {
  job_run_id: EntityId;
  dataset_run_id: EntityId | null;
  status: string;
  mean_score: string | null;
}

/** Cron 预设：UI 选项 → 表达式 + 可读描述
 *
 * `value` 是 cron 表达式；自定义模式用 `CRON_CUSTOM_SENTINEL` 哨兵
 * （Radix Select.Item 禁止 value="" 故不能用空串）。
 */
export const CRON_CUSTOM_SENTINEL = '__custom__';

export const CRON_PRESETS: { label: string; value: string; hint: string }[] = [
  { label: '每小时', value: '0 * * * *', hint: '每小时的 :00 触发' },
  { label: '每天凌晨 2 点', value: '0 2 * * *', hint: '每日 02:00 触发' },
  { label: '每天上午 9 点', value: '0 9 * * *', hint: '每日 09:00 触发' },
  { label: '每周一上午 9 点', value: '0 9 * * 1', hint: '工作日基线检查' },
  { label: '自定义', value: CRON_CUSTOM_SENTINEL, hint: '直接填写 cron 表达式（5 字段）' },
];

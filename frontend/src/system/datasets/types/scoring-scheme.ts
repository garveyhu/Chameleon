/** 评分方案 (Scoring Scheme) —— 「如何打分」的唯一答案，二选一。
 *
 * - template：引用一个保存的评分模板（多 metric 加权，版本化 freeze）
 * - judge：内联 judge 配置（6 种 judge + judge_config）
 *
 * 新建评估 wizard（立即跑）/ eval-job-form（定时）共用此结构，
 * 提交时按 mode 分流：template → eval_template_id / template_id；judge → judge + judge_config。
 */

import type { EntityId } from '@/core/types/api';

export type ScoringSchemeMode = 'template' | 'judge';

export interface ScoringScheme {
  mode: ScoringSchemeMode;
  /** mode='template' 时必有 */
  templateId?: EntityId;
  /** mode='judge' 时必有 */
  judge?: string;
  judgeConfig?: Record<string, unknown>;
}

/** 内联 judge 模式的默认初值。 */
export const defaultJudgeScheme: ScoringScheme = {
  mode: 'judge',
  judge: 'exact_match',
  judgeConfig: undefined,
};

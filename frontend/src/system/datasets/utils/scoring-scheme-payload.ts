/** ScoringScheme → 各端点提交字段的映射。
 *
 * 两条评估通路共用同一 ScoringScheme，但落到不同端点字段：
 *  - 立即跑（DatasetRun）：template → eval_template_id；judge → judge + judge_config
 *  - 定时（EvalJob）：template → template_id；judge → judge + judge_config
 * 集中在此避免两处分流逻辑漂移。
 */

import type { EntityId } from '@/core/types/api';
import type { ScoringScheme } from '@/system/datasets/types/scoring-scheme';

interface RunSchemeFields {
  judge: string;
  judge_config?: Record<string, unknown>;
  eval_template_id?: EntityId;
}

interface JobSchemeFields {
  judge: string;
  judge_config: Record<string, unknown> | null;
  template_id: EntityId | null;
}

/** DatasetRun 立即跑入参。模板模式仍带占位 judge（后端按 eval_template_id 覆盖评分）。 */
export const schemeToRunFields = (scheme: ScoringScheme): RunSchemeFields => {
  if (scheme.mode === 'template' && scheme.templateId != null) {
    return { judge: 'exact_match', eval_template_id: scheme.templateId };
  }
  return {
    judge: scheme.judge ?? 'exact_match',
    judge_config: scheme.judgeConfig,
  };
};

/** EvalJob 定时入参。模板模式 template_id 非空、judge 占位；judge 模式 template_id=0 解绑。 */
export const schemeToJobFields = (scheme: ScoringScheme): JobSchemeFields => {
  if (scheme.mode === 'template' && scheme.templateId != null) {
    return {
      judge: 'exact_match',
      judge_config: null,
      template_id: scheme.templateId,
    };
  }
  return {
    judge: scheme.judge ?? 'exact_match',
    judge_config: scheme.judgeConfig ?? null,
    template_id: 0 as unknown as EntityId,
  };
};

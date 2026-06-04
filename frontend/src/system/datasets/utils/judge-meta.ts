/** 评分器（judge）共享元数据 —— 中文名 + 说明（量纲提示）+ 配置形态。
 *
 * 供评分方案选择器（scoring-scheme-picker）与各评估表单同用，
 * 避免两份 JUDGE_META 漂移。后端 6 个 judge 见 GET /v1/admin/datasets/judges。
 */

/** judge 的「评分配置区」渲染形态：
 *  - none      → 无配置（exact_match / contains / llm_judge）
 *  - criteria  → 多行 criteria 文本（llm_score）
 *  - reference → 只读说明，对照 reference_output（gsb）
 *  - dsl       → 多行 DSL 文本（规则 DSL，逐字段 + 自然语言规则）
 */
export type JudgeConfigKind = 'none' | 'criteria' | 'reference' | 'dsl';

export interface JudgeMeta {
  label: string;
  desc: string;
  config: JudgeConfigKind;
}

export const JUDGE_META: Record<string, JudgeMeta> = {
  exact_match: {
    label: '精确匹配',
    desc: '模型回答与理想回答完全一致才算对（0 / 1 二值）',
    config: 'none',
  },
  contains: {
    label: '包含匹配',
    desc: '理想回答作为子串出现在模型回答里即算对（0 / 1 二值）',
    config: 'none',
  },
  llm_judge: {
    label: 'AI 评分（二元）',
    desc: '由大模型对比理想 / 实际回答打分并给出理由（语义级 0–1 连续分）',
    config: 'none',
  },
  llm_score: {
    label: 'AI 评分（1-5）',
    desc: '按你给的评分要点逐项打 1–5 档，归一为 0–1 分',
    config: 'criteria',
  },
  gsb: {
    label: 'GSB 对比',
    desc: '对比每条样本的【参照回答 reference_output】判定 好 / 平 / 差',
    config: 'reference',
  },
  dsl: {
    label: '规则 DSL',
    desc: '用规则 DSL 逐字段 + 自然语言规则打分，加权归一为 0–1 分',
    config: 'dsl',
  },
};

/** 取某 judge 的配置形态；未知 judge 退回 none。 */
export const judgeConfigKind = (judge: string): JudgeConfigKind =>
  JUDGE_META[judge]?.config ?? 'none';

/** judge 标签；未知 judge 退回原始 key。 */
export const judgeLabel = (judge: string): string =>
  JUDGE_META[judge]?.label ?? judge;

/** 把表单态组装成提交用的 judge_config。
 *  - criteria（llm_score）→ { criteria }（空则空对象）
 *  - dsl → { dsl }（空文本则空对象）
 *  - reference → {}
 *  - none → undefined（不传）
 */
export const buildJudgeConfig = (
  judge: string,
  criteria: string,
  dslText = '',
): Record<string, unknown> | undefined => {
  const kind = judgeConfigKind(judge);
  if (kind === 'criteria') {
    const trimmed = criteria.trim();
    return trimmed ? { criteria: trimmed } : {};
  }
  if (kind === 'dsl') {
    const trimmed = dslText.trim();
    return trimmed ? { dsl: trimmed } : {};
  }
  if (kind === 'reference') return {};
  return undefined;
};

/** 从已存的 judge_config 回填 criteria 文本（编辑场景）。 */
export const readCriteria = (
  judgeConfig: Record<string, unknown> | null | undefined,
): string => {
  const c = judgeConfig?.criteria;
  return typeof c === 'string' ? c : '';
};

/** 从已存的 judge_config 回填 DSL 文本（编辑场景）。 */
export const readDslText = (
  judgeConfig: Record<string, unknown> | null | undefined,
): string => {
  const d = judgeConfig?.dsl;
  return typeof d === 'string' ? d : '';
};

/** 评分配置区 —— 按所选 judge 条件渲染配置输入。
 *
 * 受控组件：上层持有 criteria 字符串，本组件只出 UI。提交时上层用
 * buildJudgeConfig 组装 judge_config。run-start-modal 与 eval-job-form-modal 同用。
 */

import { Label } from '@/core/components/ui/label';
import { Textarea } from '@/core/components/ui/textarea';
import { judgeConfigKind } from '@/system/datasets/utils/judge-meta';

interface JudgeConfigFieldsProps {
  judge: string;
  /** llm_score 的 criteria 文本（多行） */
  criteria: string;
  onCriteriaChange: (value: string) => void;
}

export const JudgeConfigFields = ({
  judge,
  criteria,
  onCriteriaChange,
}: JudgeConfigFieldsProps) => {
  const kind = judgeConfigKind(judge);
  if (kind === 'none') return null;

  return (
    <div className="rounded-md border border-stone-200/70 bg-stone-50/40 p-3 space-y-2">
      <div className="text-[11.5px] font-medium text-stone-700">评分配置</div>

      {kind === 'criteria' && (
        <div className="space-y-1.5">
          <Label>评分要点</Label>
          <Textarea
            value={criteria}
            onChange={e => onCriteriaChange(e.target.value)}
            placeholder={'1. 是否覆盖要点\n2. 语气是否专业\n3. 有无事实错误'}
            rows={4}
            className="text-[12.5px]"
          />
          <p className="text-[10.5px] leading-snug text-stone-400">
            每行一条要点；大模型按要点逐项打 1–5 档后归一为 0–1 分
          </p>
        </div>
      )}

      {kind === 'reference' && (
        <p className="text-[11.5px] leading-relaxed text-stone-500">
          将对比每条样本的
          <span className="mx-1 rounded bg-white px-1 py-0.5 font-mono text-[10.5px] text-stone-600">
            reference_output
          </span>
          参照回答，判定模型回答 好 / 平 / 差（G / S / B）。无需额外配置，
          请确保样本已带参照回答。
        </p>
      )}

      {kind === 'upcoming' && (
        <p className="text-[11.5px] leading-relaxed text-amber-600">
          规则 DSL 评分即将上线（解析器尚未接入），暂不可用，请先选用其它评分方式。
        </p>
      )}
    </div>
  );
};

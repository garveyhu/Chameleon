/** 评分方案选择器 —— 「如何打分」的统一入口（方案C 核心）。
 *
 * 两种模式 tab：
 *  1) 选已有模板：拉 eval-templates 列表下拉 + 展示该模板 metrics/阈值
 *  2) 自定义评分：复用 JudgeConfigFields（judge 下拉 + criteria / gsb / dsl）
 *
 * 受控组件：上层持 ScoringScheme（mode + templateId? / judge? + judgeConfig?），
 * 本组件只出 UI + 回吐变更。criteria / dsl 文本为本组件内部态，变更时即时组装回
 * judgeConfig 并上抛。eval-job-form / 新建评估 wizard 共用。
 */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { Badge } from '@/core/components/ui/badge';
import { Label } from '@/core/components/ui/label';
import { SegmentedControl } from '@/core/components/ui/segmented-control';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import type { EntityId } from '@/core/types/api';
import { JudgeConfigFields } from '@/system/datasets/components/judge-config-fields';
import { evalTemplateApi } from '@/system/datasets/services/eval-template';
import type { EvalTemplateItem } from '@/system/datasets/types/eval-template';
import type {
  ScoringScheme,
  ScoringSchemeMode,
} from '@/system/datasets/types/scoring-scheme';
import {
  buildJudgeConfig,
  JUDGE_META,
  readCriteria,
  readDslText,
} from '@/system/datasets/utils/judge-meta';

interface ScoringSchemePickerProps {
  value: ScoringScheme;
  onChange: (next: ScoringScheme) => void;
  /** judge 列表（来自 /judges query；空则退回内置默认） */
  judges?: string[];
}

export const ScoringSchemePicker = ({
  value,
  onChange,
  judges,
}: ScoringSchemePickerProps) => {
  // criteria / dsl 文本为内部态，从初值回填一次（组件每用一处独立挂载）
  const [criteria, setCriteria] = useState(() =>
    readCriteria(value.judgeConfig),
  );
  const [dslText, setDslText] = useState(() => readDslText(value.judgeConfig));

  const templatesQ = useQuery({
    queryKey: ['scoring-scheme:templates'],
    queryFn: () =>
      evalTemplateApi.list({ page: 1, page_size: 200, sort_by: 'name', order: 'asc' }),
    staleTime: 30_000,
  });
  const templates = templatesQ.data?.items ?? [];
  const selectedTemplate =
    value.mode === 'template' && value.templateId != null
      ? templates.find(t => String(t.id) === String(value.templateId)) ?? null
      : null;

  const judgeOptions = judges?.length ? judges : ['exact_match'];
  const currentJudge = value.judge ?? 'exact_match';

  const switchMode = (mode: ScoringSchemeMode) => {
    if (mode === value.mode) return;
    if (mode === 'template') {
      onChange({ mode: 'template', templateId: templates[0]?.id });
    } else {
      onChange({
        mode: 'judge',
        judge: currentJudge,
        judgeConfig: buildJudgeConfig(currentJudge, criteria, dslText),
      });
    }
  };

  const pickTemplate = (id: string) =>
    onChange({ mode: 'template', templateId: id as unknown as EntityId });

  const pickJudge = (judge: string) =>
    onChange({
      mode: 'judge',
      judge,
      judgeConfig: buildJudgeConfig(judge, criteria, dslText),
    });

  const onCriteriaChange = (next: string) => {
    setCriteria(next);
    onChange({
      mode: 'judge',
      judge: currentJudge,
      judgeConfig: buildJudgeConfig(currentJudge, next, dslText),
    });
  };
  const onDslChange = (next: string) => {
    setDslText(next);
    onChange({
      mode: 'judge',
      judge: currentJudge,
      judgeConfig: buildJudgeConfig(currentJudge, criteria, next),
    });
  };

  return (
    <div className="space-y-3">
      <Label>评分方案</Label>
      <SegmentedControl
        value={value.mode}
        onChange={switchMode}
        options={[
          { value: 'template', label: '选已有模板' },
          { value: 'judge', label: '自定义评分' },
        ]}
      />

      {value.mode === 'template' ? (
        <TemplateMode
          templates={templates}
          loading={templatesQ.isLoading}
          selectedId={value.templateId}
          selected={selectedTemplate}
          onPick={pickTemplate}
        />
      ) : (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>评分方式</Label>
            <Select value={currentJudge} onValueChange={pickJudge}>
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
            {JUDGE_META[currentJudge] && (
              <p className="text-[10.5px] leading-snug text-stone-400">
                {JUDGE_META[currentJudge].desc}
              </p>
            )}
          </div>
          <JudgeConfigFields
            judge={currentJudge}
            criteria={criteria}
            onCriteriaChange={onCriteriaChange}
            dslText={dslText}
            onDslTextChange={onDslChange}
          />
        </div>
      )}
    </div>
  );
};

const TemplateMode = ({
  templates,
  loading,
  selectedId,
  selected,
  onPick,
}: {
  templates: EvalTemplateItem[];
  loading: boolean;
  selectedId?: EntityId;
  selected: EvalTemplateItem | null;
  onPick: (id: string) => void;
}) => {
  if (loading) {
    return <p className="text-[11.5px] text-stone-400">加载评分方案…</p>;
  }
  if (templates.length === 0) {
    return (
      <p className="rounded-md border border-amber-200/70 bg-amber-50/50 px-3 py-2 text-[11.5px] leading-relaxed text-amber-700">
        还没有评分模板。先去「评分方案」页建一个多指标模板，或切到「自定义评分」直接配 judge。
      </p>
    );
  }
  return (
    <div className="space-y-2">
      <Select
        value={selectedId != null ? String(selectedId) : ''}
        onValueChange={onPick}
      >
        <SelectTrigger>
          <SelectValue placeholder="选择评分模板…" />
        </SelectTrigger>
        <SelectContent>
          {templates.map(t => (
            <SelectItem key={String(t.id)} value={String(t.id)}>
              {t.name}（v{t.version} · {t.metrics.length} 指标）
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {selected && (
        <div className="rounded-md border border-stone-200/70 bg-stone-50/40 p-3 space-y-2">
          {selected.description && (
            <p className="text-[11px] leading-snug text-stone-500">
              {selected.description}
            </p>
          )}
          <div className="flex flex-wrap gap-1">
            {selected.metrics.map((m, i) => (
              <Badge
                key={i}
                variant="outline"
                className="bg-white text-[10.5px] text-stone-600"
                title={`${m.algorithm} · 权重 ${m.weight}${
                  m.threshold != null ? ` · 阈值 ${m.threshold}` : ''
                }`}
              >
                {m.name}
                <span className="ml-1 text-stone-400">×{m.weight}</span>
                {m.threshold != null && (
                  <span className="ml-1 text-stone-400">≥{m.threshold}</span>
                )}
              </Badge>
            ))}
          </div>
          {selected.judge_provider && (
            <p className="text-[10.5px] text-stone-400">
              评判模型 · {selected.judge_provider}
            </p>
          )}
        </div>
      )}
    </div>
  );
};

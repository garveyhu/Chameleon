/** Playground 列参数面板：model / system prompt / temperature / top_p / max_tokens / kb_ids */

import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { AgentPicker } from '@/core/components/common/agent-picker';
import { Input } from '@/core/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import { agentApi } from '@/system/agents/services/agent';
import { kbApi } from '@/system/kbs/services/kb';
import { modelApi } from '@/system/models/services/model';
import type { PlaygroundParams } from '@/system/playground/types/playground';

interface Props {
  params: PlaygroundParams;
  onChange: (next: PlaygroundParams) => void;
  className?: string;
}

export const ParamPanel = ({ params, onChange, className }: Props) => {
  const modelsQ = useQuery({
    queryKey: ['playground-models'],
    queryFn: () => modelApi.list({ kind: 'chat' }),
  });
  const kbsQ = useQuery({
    queryKey: ['playground-kbs'],
    queryFn: () => kbApi.list({ page: 1, page_size: 100 }),
  });

  const models = useMemo(
    () => (modelsQ.data ?? []).filter(m => m.enabled),
    [modelsQ.data],
  );

  const set = <K extends keyof PlaygroundParams>(
    key: K,
    value: PlaygroundParams[K],
  ) => onChange({ ...params, [key]: value });

  /** 选关联应用 → 用其配置预填（应用默认 ⊕ 会话覆盖）；选「全部应用」(='') 解除关联 */
  const onPickAgent = async (agentKey: string) => {
    if (!agentKey) {
      set('bound_agent_key', null);
      return;
    }
    try {
      const cfg = await agentApi.prefillConfig(agentKey);
      const next: PlaygroundParams = { ...params, bound_agent_key: agentKey };
      // 仅可预填的应用才覆盖配置；workflow/外部应用只记录关联，不动用户现有设置
      let modelMissing = false;
      if (cfg.prefillable) {
        if (cfg.model_code) {
          const m = models.find(x => x.code === cfg.model_code);
          if (m) next.model_id = String(m.id);
          else modelMissing = true; // 应用模型当前不可用/未启用
        }
        if (cfg.system_prompt != null) next.system_prompt = cfg.system_prompt;
        // kb_ids 归一成 string（与 KB 下拉的 String(id) 一致，雪花 id 也安全）
        next.kb_ids = (cfg.kb_ids ?? []).map(String);
      }
      onChange(next);
      if (modelMissing) {
        toast.warning(`应用模型「${cfg.model_code}」当前不可用，请手动选择模型`);
      } else if (cfg.notes) {
        if (cfg.prefillable) toast.success(cfg.notes);
        else toast.info(cfg.notes);
      }
    } catch {
      toast.error('载入应用配置失败');
    }
  };

  return (
    <div className={cn('space-y-3 text-[12.5px]', className)}>
      <div>
        <label className="mb-1 block text-stone-600">关联应用（可选）</label>
        <AgentPicker
          value={params.bound_agent_key ?? ''}
          onChange={onPickAgent}
          width={232}
        />
        <p className="mt-1 text-[10.5px] leading-tight text-stone-400">
          选应用后用其模型 / 提示词 / 知识库预填，仍可手动调整
        </p>
      </div>

      <div>
        <label className="mb-1 block text-stone-600">模型</label>
        <Select
          value={params.model_id ? String(params.model_id) : ''}
          onValueChange={v => set('model_id', v)}
        >
          <SelectTrigger className="h-8">
            <SelectValue placeholder="选模型" />
          </SelectTrigger>
          <SelectContent>
            {models.map(m => (
              <SelectItem key={m.id} value={String(m.id)}>
                {m.code}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div>
        <label className="mb-1 block text-stone-600">System Prompt</label>
        <Textarea
          rows={3}
          value={params.system_prompt}
          onChange={e => set('system_prompt', e.target.value)}
          placeholder="可留空"
          className="text-[12px]"
        />
      </div>

      <div className="space-y-3">
        <NumberField
          label="Temperature"
          value={params.temperature}
          min={0}
          max={2}
          step={0.1}
          onChange={v => set('temperature', v)}
        />
        <NumberField
          label="Top P"
          value={params.top_p ?? 1}
          min={0}
          max={1}
          step={0.05}
          onChange={v => set('top_p', v)}
        />
        <NumberField
          label="Max Tokens"
          value={params.max_tokens ?? 0}
          min={0}
          max={8192}
          step={64}
          onChange={v => set('max_tokens', v > 0 ? v : null)}
          allowEmpty
        />
      </div>

      <div>
        <label className="mb-1 block text-stone-600">关联 KB（多选）</label>
        <Select
          value={params.kb_ids.length > 0 ? String(params.kb_ids[0]) : ''}
          onValueChange={v => {
            const next = params.kb_ids.includes(v)
              ? params.kb_ids.filter(k => k !== v)
              : [...params.kb_ids, v];
            set('kb_ids', next);
          }}
        >
          <SelectTrigger className="h-8">
            <SelectValue placeholder={params.kb_ids.length > 0 ? `已选 ${params.kb_ids.length} 个` : '未关联'} />
          </SelectTrigger>
          <SelectContent>
            {(kbsQ.data?.items ?? []).map(k => (
              <SelectItem key={k.id} value={String(k.id)}>
                {params.kb_ids.includes(k.id) ? '✓ ' : '  '}
                {k.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {params.kb_ids.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {params.kb_ids.map(id => {
              const kb = (kbsQ.data?.items ?? []).find(k => k.id === id);
              return (
                <span
                  key={id}
                  className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[10.5px] text-amber-700"
                >
                  {kb?.name ?? `#${id}`}
                  <button
                    type="button"
                    onClick={() =>
                      set('kb_ids', params.kb_ids.filter(k => k !== id))
                    }
                  >
                    ×
                  </button>
                </span>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

interface NumberFieldProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  allowEmpty?: boolean;
}

const NumberField = ({
  label,
  value,
  min,
  max,
  step,
  onChange,
  allowEmpty,
}: NumberFieldProps) => (
  <div className="flex items-center justify-between gap-2">
    <span className="text-stone-600">{label}</span>
    <Input
      type="number"
      min={min}
      max={max}
      step={step}
      value={allowEmpty && value === 0 ? '' : value}
      placeholder={allowEmpty ? '∞' : undefined}
      onChange={e => onChange(e.target.value === '' ? 0 : Number(e.target.value))}
      className="!h-7 !w-20 text-right text-[12px] tnum"
    />
  </div>
);

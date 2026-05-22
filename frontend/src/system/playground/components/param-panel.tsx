/** Playground 列参数面板：model / system prompt / temperature / top_p / max_tokens / kb_ids */

import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
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

  return (
    <div className={cn('space-y-3 text-[12.5px]', className)}>
      <div>
        <label className="mb-1 block text-stone-600">模型</label>
        <Select
          value={params.model_id ? String(params.model_id) : ''}
          onValueChange={v => set('model_id', Number(v))}
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

      <div className="grid grid-cols-3 gap-2">
        <NumberField
          label="temperature"
          value={params.temperature}
          min={0}
          max={2}
          step={0.1}
          onChange={v => set('temperature', v)}
        />
        <NumberField
          label="top_p"
          value={params.top_p ?? 1}
          min={0}
          max={1}
          step={0.05}
          onChange={v => set('top_p', v)}
        />
        <NumberField
          label="max_tokens"
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
            const id = Number(v);
            const next = params.kb_ids.includes(id)
              ? params.kb_ids.filter(k => k !== id)
              : [...params.kb_ids, id];
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
  <div>
    <label className="mb-1 block text-stone-600">
      {label} = <span className="font-mono tnum">{allowEmpty && value === 0 ? '∞' : value}</span>
    </label>
    <input
      type="range"
      min={min}
      max={max}
      step={step}
      value={value}
      onChange={e => onChange(Number(e.target.value))}
      className="w-full accent-amber-600"
    />
  </div>
);

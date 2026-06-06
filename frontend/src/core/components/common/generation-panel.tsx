/** GenerationPanel —— 媒体生成的统一参数面板（声明式驱动）
 *
 * 按后端 param-spec 动态渲染：提示词 + 风格预设 + 比例/数量等基础参数 + 高级折叠。
 * 模型测试、Playground（生图/视频应用）、文生图工作台共用。通过 ref.getRequest()
 * 取 { prompt(已拼风格), params }。
 */

import { useQuery } from '@tanstack/react-query';
import { Dices } from 'lucide-react';
import { forwardRef, useImperativeHandle, useMemo, useState } from 'react';

import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import type { EntityId } from '@/core/types/api';
import { imagegenApi, type ParamField } from '@/system/models/services/imagegen';

export interface GenerationRequest {
  prompt: string;
  params: Record<string, unknown>;
}

export interface GenerationPanelHandle {
  getRequest: () => GenerationRequest;
}

interface Props {
  modelId: EntityId;
  disabled?: boolean;
  promptPlaceholder?: string;
}

const chipCls = (active: boolean) =>
  cn(
    'rounded-full border px-2.5 py-1 text-[11.5px] transition',
    active
      ? 'border-violet-500 bg-violet-50 text-violet-700'
      : 'border-stone-200 text-stone-600 hover:border-stone-300',
  );

export const GenerationPanel = forwardRef<GenerationPanelHandle, Props>(
  ({ modelId, disabled, promptPlaceholder }, ref) => {
    const [prompt, setPrompt] = useState('');
    const [styleId, setStyleId] = useState('none');
    const [params, setParams] = useState<Record<string, unknown>>({});
    const [showAdvanced, setShowAdvanced] = useState(false);

    const q = useQuery({
      queryKey: ['mediagen-param-spec', String(modelId)],
      queryFn: () => imagegenApi.getParamSpec(modelId),
      staleTime: 30_000,
    });
    const fields = useMemo(() => q.data?.fields ?? [], [q.data]);
    const styles = useMemo(() => q.data?.styles ?? [], [q.data]);

    const valOf = (f: ParamField) => params[f.key] ?? f.default;
    const setVal = (k: string, v: unknown) => setParams(p => ({ ...p, [k]: v }));

    useImperativeHandle(
      ref,
      () => ({
        getRequest: () => {
          const merged: Record<string, unknown> = {};
          for (const f of fields) {
            const v = params[f.key] ?? f.default;
            if (v !== undefined && v !== null && v !== '') merged[f.key] = v;
          }
          const suffix = styles.find(s => s.id === styleId)?.suffix ?? '';
          const base = prompt.trim();
          const finalPrompt = suffix ? (base ? `${base}, ${suffix}` : suffix) : base;
          return { prompt: finalPrompt, params: merged };
        },
      }),
      [fields, params, styles, styleId, prompt],
    );

    const basic = fields.filter(f => f.group === 'basic');
    const advanced = fields.filter(f => f.group === 'advanced');

    return (
      <div className="space-y-3">
        <div className="space-y-1.5">
          <Label className="text-[12px] text-stone-600">提示词</Label>
          <Textarea
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            disabled={disabled}
            rows={3}
            placeholder={promptPlaceholder ?? '描述你想生成的画面…'}
            className="text-[12.5px]"
          />
        </div>

        {styles.length ? (
          <div className="space-y-1.5">
            <Label className="text-[12px] text-stone-600">风格</Label>
            <div className="flex flex-wrap gap-1.5">
              {styles.map(s => (
                <button
                  key={s.id}
                  type="button"
                  disabled={disabled}
                  onClick={() => setStyleId(s.id)}
                  className={chipCls(styleId === s.id)}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {basic.map(f => (
          <FieldControl
            key={f.key}
            field={f}
            value={valOf(f)}
            onChange={v => setVal(f.key, v)}
            disabled={disabled}
          />
        ))}

        {advanced.length ? (
          <div className="border-t border-stone-100 pt-2">
            <button
              type="button"
              onClick={() => setShowAdvanced(s => !s)}
              className="text-[11.5px] text-stone-500 transition hover:text-stone-700"
            >
              {showAdvanced ? '▾ 收起高级参数' : '▸ 高级参数'}
            </button>
            {showAdvanced ? (
              <div className="mt-2 space-y-3">
                {advanced.map(f => (
                  <FieldControl
                    key={f.key}
                    field={f}
                    value={valOf(f)}
                    onChange={v => setVal(f.key, v)}
                    disabled={disabled}
                  />
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  },
);
GenerationPanel.displayName = 'GenerationPanel';

const FieldControl = ({
  field,
  value,
  onChange,
  disabled,
}: {
  field: ParamField;
  value: unknown;
  onChange: (v: unknown) => void;
  disabled?: boolean;
}) => {
  const label = <Label className="text-[12px] text-stone-600">{field.label}</Label>;

  if (field.type === 'aspect_ratio') {
    const opts = field.options ?? [];
    const cur = String(value ?? '');
    const isPreset = opts.some(o => o.value === cur);
    const isCustom = field.custom && !!cur && !isPreset;
    const [cw, ch] = cur.includes('*') ? cur.split('*') : ['', ''];
    const lo = field.min ?? 512;
    const hi = field.max ?? 2048;
    return (
      <div className="space-y-1.5">
        {label}
        <div className="flex flex-wrap gap-1.5">
          {opts.map(o => (
            <button
              key={o.value}
              type="button"
              disabled={disabled}
              onClick={() => onChange(o.value)}
              className={chipCls(cur === o.value)}
            >
              {o.label}
            </button>
          ))}
          {field.custom ? (
            <button
              type="button"
              disabled={disabled}
              onClick={() => onChange(isCustom ? cur : `${hi}*${hi}`)}
              className={chipCls(!!isCustom)}
            >
              自定义
            </button>
          ) : null}
        </div>
        {isCustom ? (
          <div className="flex items-center gap-1.5">
            <Input
              type="number"
              min={lo}
              max={hi}
              value={cw}
              disabled={disabled}
              onChange={e => onChange(`${e.target.value || lo}*${ch || lo}`)}
              className="h-8 text-[12px]"
              placeholder="宽"
            />
            <span className="text-stone-400">×</span>
            <Input
              type="number"
              min={lo}
              max={hi}
              value={ch}
              disabled={disabled}
              onChange={e => onChange(`${cw || lo}*${e.target.value || lo}`)}
              className="h-8 text-[12px]"
              placeholder="高"
            />
            <span className="ml-1 shrink-0 text-[10.5px] text-stone-400">px（{lo}–{hi}）</span>
          </div>
        ) : null}
      </div>
    );
  }

  if (field.type === 'select') {
    return (
      <div className="space-y-1.5">
        {label}
        <Select value={String(value ?? '')} onValueChange={onChange} disabled={disabled}>
          <SelectTrigger className="h-8 text-[12px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(field.options ?? []).map(o => (
              <SelectItem key={o.value} value={o.value} className="text-[12px]">
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    );
  }

  if (field.type === 'toggle') {
    return (
      <label className="flex items-center gap-2 text-[12px] text-stone-700">
        <input
          type="checkbox"
          checked={!!value}
          disabled={disabled}
          onChange={e => onChange(e.target.checked)}
        />
        {field.label}
      </label>
    );
  }

  if (field.type === 'text') {
    return (
      <div className="space-y-1.5">
        {label}
        <Textarea
          value={String(value ?? '')}
          rows={2}
          disabled={disabled}
          onChange={e => onChange(e.target.value)}
          className="text-[12px]"
        />
      </div>
    );
  }

  if (field.type === 'seed') {
    return (
      <div className="space-y-1.5">
        {label}
        <div className="flex gap-1.5">
          <Input
            type="number"
            value={value == null ? '' : String(value)}
            placeholder="随机"
            disabled={disabled}
            onChange={e => onChange(e.target.value ? Number(e.target.value) : null)}
            className="h-8 text-[12px]"
          />
          <button
            type="button"
            disabled={disabled}
            onClick={() => onChange(Math.floor(Math.random() * 2147483647))}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-stone-200 text-stone-500 transition hover:border-stone-300"
            title="随机种子"
          >
            <Dices className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    );
  }

  // int / float
  return (
    <div className="space-y-1.5">
      {label}
      <Input
        type="number"
        min={field.min}
        max={field.max}
        step={field.type === 'float' ? 0.1 : 1}
        value={value == null ? '' : String(value)}
        disabled={disabled}
        onChange={e => onChange(e.target.value === '' ? undefined : Number(e.target.value))}
        className="h-8 text-[12px]"
      />
    </div>
  );
};

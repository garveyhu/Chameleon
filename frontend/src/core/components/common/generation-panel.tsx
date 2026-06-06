/** GenerationPanel —— 媒体生成的统一参数面板（声明式驱动）
 *
 * 按后端 param-spec 动态渲染：提示词 + 风格预设 + 比例/数量等基础参数 + 高级折叠。
 * 模型测试、Playground（生图/视频应用）、文生图工作台共用。通过 ref.getRequest()
 * 取 { prompt(已拼风格), params }。
 */

import { useQuery } from '@tanstack/react-query';
import { Dices, ImagePlus, Loader2, X } from 'lucide-react';
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';

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
import { uploadFile } from '@/system/files/services/file-upload';
import { imagegenApi, type ParamField } from '@/system/models/services/imagegen';

export interface GenerationRequest {
  prompt: string;
  params: Record<string, unknown>;
  /** video(i2v) 首帧/参考图 url */
  input_images: string[];
}

export interface GenerationPanelHandle {
  getRequest: () => GenerationRequest;
}

interface Props {
  modelId: EntityId;
  disabled?: boolean;
  promptPlaceholder?: string;
  /** 隐藏提示词输入（Playground 等场景提示词走聊天框，仅本面板调参数） */
  hidePrompt?: boolean;
  /** 参数/风格/首帧变化时回调（受控场景：把 params + input_images 提升到父级） */
  onChange?: (req: GenerationRequest) => void;
}

const chipCls = (active: boolean) =>
  cn(
    'rounded-full border px-2.5 py-1 text-[11.5px] transition',
    active
      ? 'border-violet-500 bg-violet-50 text-violet-700'
      : 'border-stone-200 text-stone-600 hover:border-stone-300',
  );

export const GenerationPanel = forwardRef<GenerationPanelHandle, Props>(
  ({ modelId, disabled, promptPlaceholder, hidePrompt, onChange }, ref) => {
    const [prompt, setPrompt] = useState('');
    const [styleId, setStyleId] = useState('none');
    const [params, setParams] = useState<Record<string, unknown>>({});
    const [showAdvanced, setShowAdvanced] = useState(false);
    const [firstFrame, setFirstFrame] = useState('');
    const [uploading, setUploading] = useState(false);
    const fileRef = useRef<HTMLInputElement | null>(null);

    const q = useQuery({
      queryKey: ['mediagen-param-spec', String(modelId)],
      queryFn: () => imagegenApi.getParamSpec(modelId),
      staleTime: 30_000,
    });
    const mediaKind = q.data?.media_kind;
    const fields = useMemo(() => q.data?.fields ?? [], [q.data]);
    const styles = useMemo(() => q.data?.styles ?? [], [q.data]);

    const onPickFile = async (file: File | undefined) => {
      if (!file) return;
      setUploading(true);
      try {
        const r = await uploadFile(file, { namespace: 'mediagen-input' });
        setFirstFrame(r.object_url);
      } finally {
        setUploading(false);
      }
    };

    const valOf = (f: ParamField) => params[f.key] ?? f.default;
    const setVal = (k: string, v: unknown) => setParams(p => ({ ...p, [k]: v }));

    const buildRequest = (): GenerationRequest => {
      const merged: Record<string, unknown> = {};
      for (const f of fields) {
        const v = params[f.key] ?? f.default;
        if (v !== undefined && v !== null && v !== '') merged[f.key] = v;
      }
      const suffix = styles.find(s => s.id === styleId)?.suffix ?? '';
      const base = prompt.trim();
      const finalPrompt = suffix ? (base ? `${base}, ${suffix}` : suffix) : base;
      return {
        prompt: finalPrompt,
        params: merged,
        input_images: firstFrame ? [firstFrame] : [],
      };
    };

    // eslint-disable-next-line react-hooks/exhaustive-deps
    useImperativeHandle(ref, () => ({ getRequest: buildRequest }), [
      fields,
      params,
      styles,
      styleId,
      prompt,
      firstFrame,
    ]);

    // 受控场景：参数/风格/首帧变化时把结果提升到父级（提示词由父级聊天框另给）
    useEffect(() => {
      onChange?.(buildRequest());
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [fields, params, styleId, firstFrame]);

    const basic = fields.filter(f => f.group === 'basic');
    const advanced = fields.filter(f => f.group === 'advanced');

    return (
      <div className="space-y-3">
        {mediaKind === 'video' ? (
          <div className="space-y-1.5">
            <Label className="text-[12px] text-stone-600">首帧图（图生视频必填）</Label>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={e => onPickFile(e.target.files?.[0] ?? undefined)}
            />
            {firstFrame ? (
              <div className="relative inline-block">
                <img
                  src={firstFrame}
                  alt="首帧"
                  className="h-24 w-auto rounded-md border border-stone-200 object-cover"
                />
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => setFirstFrame('')}
                  className="absolute -top-2 -right-2 flex h-5 w-5 items-center justify-center rounded-full bg-stone-700 text-white"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ) : (
              <button
                type="button"
                disabled={disabled || uploading}
                onClick={() => fileRef.current?.click()}
                className="flex h-24 w-32 flex-col items-center justify-center gap-1 rounded-md border border-dashed border-stone-300 text-stone-400 transition hover:border-stone-400"
              >
                {uploading ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <ImagePlus className="h-5 w-5" />
                )}
                <span className="text-[11px]">{uploading ? '上传中…' : '上传首帧图'}</span>
              </button>
            )}
          </div>
        ) : null}

        {hidePrompt ? null : (
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
        )}

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

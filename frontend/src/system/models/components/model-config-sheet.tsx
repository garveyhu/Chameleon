/** 模型配置抽屉 —— 编辑模型的运行参数（defaults）/ 向量维度 / 启用状态。
 *
 * chat 模型：temperature / top_p / max_tokens 三个滑块；embedding 模型：dim。
 * 取代原先只读的 defaults JSON 展示 —— 真正可编辑配置。
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { ParamSlider } from '@/core/components/ui/param-slider';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import { Switch } from '@/core/components/ui/switch';
import { toast } from '@/core/lib/toast';
import { modelApi } from '@/system/models/services/model';
import type { ModelItem } from '@/system/models/types/model';

interface Props {
  model: ModelItem | null;
  onClose: () => void;
}

const numOr = (v: unknown, fallback: number): number =>
  typeof v === 'number' ? v : fallback;

export const ModelConfigSheet = ({ model, onClose }: Props) => {
  const qc = useQueryClient();
  const [temperature, setTemperature] = useState(0.7);
  const [topP, setTopP] = useState(1);
  const [maxTokens, setMaxTokens] = useState(0);
  const [dim, setDim] = useState('');
  const [enabled, setEnabled] = useState(true);

  useEffect(() => {
    if (!model) return;
    const d = model.defaults || {};
    setTemperature(numOr(d.temperature, 0.7));
    setTopP(numOr(d.top_p, 1));
    setMaxTokens(numOr(d.max_tokens, 0));
    setDim(model.dim != null ? String(model.dim) : '');
    setEnabled(model.enabled);
  }, [model]);

  const saveMut = useMutation({
    mutationFn: () => {
      const defaults: Record<string, unknown> = { temperature, top_p: topP };
      if (maxTokens > 0) defaults.max_tokens = maxTokens;
      return modelApi.update(model!.id, {
        defaults,
        dim: model!.kind === 'embedding' && dim ? Number(dim) : undefined,
        enabled,
      });
    },
    onSuccess: () => {
      toast.success('模型配置已保存');
      qc.invalidateQueries({ queryKey: ['models'] });
      onClose();
    },
  });

  return (
    <Sheet open={!!model} onOpenChange={o => !o && onClose()}>
      <SheetContent>
        {model && (
          <>
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2">
                <span className="font-mono text-[15px]">{model.code}</span>
                <Badge variant="primary">{model.kind}</Badge>
              </SheetTitle>
              <SheetDescription>
                provider: {model.provider_code || '?'} · 配置运行参数与启用状态
              </SheetDescription>
            </SheetHeader>

            <SheetBody className="space-y-5">
              {model.kind === 'chat' ? (
                <>
                  <ParamSlider
                    label="Temperature"
                    value={temperature}
                    min={0}
                    max={2}
                    step={0.1}
                    onChange={setTemperature}
                    hint="越高越随机发散，越低越确定"
                  />
                  <ParamSlider
                    label="Top P"
                    value={topP}
                    min={0}
                    max={1}
                    step={0.05}
                    onChange={setTopP}
                    hint="核采样概率阈值"
                  />
                  <ParamSlider
                    label="Max Tokens"
                    value={maxTokens}
                    min={0}
                    max={8000}
                    step={100}
                    onChange={setMaxTokens}
                    infinityAtZero
                    hint="单次回复最大 token，0 = 不限"
                  />
                </>
              ) : (
                <div className="space-y-1.5">
                  <label className="text-[12px] font-medium text-stone-700">
                    向量维度 (dim)
                  </label>
                  <Input
                    type="number"
                    value={dim}
                    onChange={e => setDim(e.target.value)}
                    placeholder="1536"
                    className="font-mono"
                  />
                  <p className="text-[10.5px] leading-snug text-stone-500">
                    embedding 向量维度，需与 KB 配置一致
                  </p>
                </div>
              )}

              <div className="flex items-center justify-between rounded-lg border border-stone-200 px-3 py-2.5">
                <div>
                  <div className="text-[12.5px] font-medium text-stone-800">启用</div>
                  <div className="text-[11px] text-stone-500">
                    关闭后该模型不可被调用
                  </div>
                </div>
                <Switch checked={enabled} onCheckedChange={setEnabled} />
              </div>
            </SheetBody>

            <SheetFooter>
              <Button variant="ghost" size="sm" onClick={onClose}>
                取消
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => saveMut.mutate()}
                disabled={saveMut.isPending}
              >
                {saveMut.isPending ? '保存中…' : '保存配置'}
              </Button>
            </SheetFooter>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
};

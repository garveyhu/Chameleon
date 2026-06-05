/** 模型配置抽屉 —— 编辑模型的运行参数 / 向量维度 / 上游映射 / 能力 / 启用状态。
 *
 * chat：temperature / top_p / max_tokens 三滑块 + 能力（vision/tool/json/ctx）；
 * embedding：dim + batch_size。所有模型：upstream_name（经 new-api 网关时用）。
 *
 * 表单主体抽成 ModelConfigForm，按 model.id remount（key）+ 状态从 model 初始化，
 * 避免 useEffect 同步 props（react-hooks/set-state-in-effect）。外层 Sheet 保持挂载做开合动画。
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

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
import type { ModelCapabilities, ModelItem } from '@/system/models/types/model';

interface Props {
  model: ModelItem | null;
  onClose: () => void;
}

const numOr = (v: unknown, fallback: number): number =>
  typeof v === 'number' ? v : fallback;

export const ModelConfigSheet = ({ model, onClose }: Props) => (
  <Sheet open={!!model} onOpenChange={o => !o && onClose()}>
    <SheetContent>
      {model && <ModelConfigForm key={model.id} model={model} onClose={onClose} />}
    </SheetContent>
  </Sheet>
);

const ModelConfigForm = ({
  model,
  onClose,
}: {
  model: ModelItem;
  onClose: () => void;
}) => {
  const qc = useQueryClient();
  const d = model.defaults || {};
  const c = model.capabilities || {};
  const [temperature, setTemperature] = useState(numOr(d.temperature, 0.7));
  const [topP, setTopP] = useState(numOr(d.top_p, 1));
  const [maxTokens, setMaxTokens] = useState(numOr(d.max_tokens, 0));
  const [dim, setDim] = useState(model.dim != null ? String(model.dim) : '');
  const [batchSize, setBatchSize] = useState(
    d.batch_size != null ? String(d.batch_size) : '',
  );
  const [enabled, setEnabled] = useState(model.enabled);
  const [upstreamName, setUpstreamName] = useState(model.upstream_name || '');
  const [vision, setVision] = useState(!!c.vision);
  const [toolCall, setToolCall] = useState(!!c.tool_call);
  const [jsonMode, setJsonMode] = useState(!!c.json_mode);
  const [contextWindow, setContextWindow] = useState(
    c.context_window != null ? String(c.context_window) : '',
  );

  const saveMut = useMutation({
    mutationFn: () => {
      const isChat = model.kind === 'chat';
      // chat 存运行参数；embedding 存 batch_size —— 各存各的，不互相污染 defaults
      const defaults: Record<string, unknown> = isChat
        ? { temperature, top_p: topP, ...(maxTokens > 0 ? { max_tokens: maxTokens } : {}) }
        : { ...(batchSize ? { batch_size: Number(batchSize) } : {}) };
      const capabilities: ModelCapabilities = {
        vision,
        tool_call: toolCall,
        json_mode: jsonMode,
      };
      if (contextWindow) capabilities.context_window = Number(contextWindow);
      return modelApi.update(model.id, {
        defaults,
        dim: model.kind === 'embedding' && dim ? Number(dim) : undefined,
        enabled,
        upstream_name: upstreamName.trim(),
        capabilities: isChat ? capabilities : undefined,
      });
    },
    onSuccess: () => {
      toast.success('模型配置已保存');
      qc.invalidateQueries({ queryKey: ['models'] });
      onClose();
    },
  });

  return (
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
          <>
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
            <div className="space-y-1.5">
              <label className="text-[12px] font-medium text-stone-700">
                批量大小 (batch_size)
              </label>
              <Input
                type="number"
                value={batchSize}
                onChange={e => setBatchSize(e.target.value)}
                placeholder="25"
                className="font-mono"
              />
              <p className="text-[10.5px] leading-snug text-stone-500">
                单次请求最多 embed 多少条；留空用默认 25（DashScope 上限）
              </p>
            </div>
          </>
        )}

        <div className="space-y-1.5">
          <label className="text-[12px] font-medium text-stone-700">
            上游模型名 (upstream_name)
          </label>
          <Input
            value={upstreamName}
            onChange={e => setUpstreamName(e.target.value)}
            placeholder={model.code}
            className="font-mono"
          />
          <p className="text-[10.5px] leading-snug text-stone-500">
            经网关(new-api)时打给上游的模型名；留空用 code「{model.code}」
          </p>
        </div>

        {model.kind === 'chat' && (
          <div className="space-y-2.5 rounded-lg border border-stone-200 px-3 py-3">
            <div className="text-[12px] font-medium text-stone-700">能力</div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-stone-700">视觉 (vision)</span>
              <Switch checked={vision} onCheckedChange={setVision} />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-stone-700">工具调用 (tool call)</span>
              <Switch checked={toolCall} onCheckedChange={setToolCall} />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-stone-700">JSON 模式</span>
              <Switch checked={jsonMode} onCheckedChange={setJsonMode} />
            </div>
            <div className="space-y-1.5 pt-1">
              <label className="text-[12px] text-stone-700">
                上下文窗口 (tokens)
              </label>
              <Input
                type="number"
                value={contextWindow}
                onChange={e => setContextWindow(e.target.value)}
                placeholder="128000"
                className="font-mono"
              />
            </div>
          </div>
        )}

        <div className="flex items-center justify-between rounded-lg border border-stone-200 px-3 py-2.5">
          <div>
            <div className="text-[12.5px] font-medium text-stone-800">启用</div>
            <div className="text-[11px] text-stone-500">关闭后该模型不可被调用</div>
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
  );
};

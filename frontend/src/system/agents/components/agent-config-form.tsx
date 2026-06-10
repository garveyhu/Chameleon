/** Agent 参数表单 —— 按 @agent(config=[Opt(...)]) 声明自动渲染（string/number/boolean/select）。
 *
 * 仅声明了 config 的 agentkit 智能体显示；值存 agents.config["opts"]，运行时进 ctx.config。
 * 不依赖 effect 同步：本地只存编辑覆盖，生效值 = 覆盖 ?? 服务端值 ?? Opt.default。
 */
import { useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Save, SlidersHorizontal } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { Switch } from '@/core/components/ui/switch';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { agentApi } from '@/system/agents/services/agent';
import type { ConfigOptionItem } from '@/system/agents/types/agent';

interface Props {
  agentId: EntityId;
}

export const AgentConfigForm = ({ agentId }: Props) => {
  const qc = useQueryClient();
  const schemaQ = useQuery({
    queryKey: ['agent-config-schema', agentId],
    queryFn: () => agentApi.configSchema(agentId),
  });
  const [edits, setEdits] = useState<Record<string, unknown>>({});

  const options = schemaQ.data?.options ?? [];
  const values = schemaQ.data?.values ?? {};

  const effective = (o: ConfigOptionItem): unknown => {
    if (o.key in edits) return edits[o.key];
    if (o.key in values) return values[o.key];
    return o.default ?? (o.type === 'boolean' ? false : '');
  };

  const saveMut = useMutation({
    mutationFn: () => {
      // 仅提交「服务端已存值 + 本次编辑」——未动过的 Opt.default 不落库，
      // 作者日后改代码默认值仍生效（避免保存把默认值固化进 DB）
      const payload: Record<string, unknown> = { ...values };
      for (const [k, v] of Object.entries(edits)) payload[k] = v;
      for (const o of options) {
        const v = payload[o.key];
        // number 清空 = 回落代码默认：删键（后端按提交值全量替换 opts）
        if (o.type === 'number' && (v === '' || (typeof v === 'number' && Number.isNaN(v)))) {
          delete payload[o.key];
        }
      }
      return agentApi.updateConfig(agentId, payload);
    },
    onSuccess: () => {
      setEdits({});
      toast.success('参数已保存');
      qc.invalidateQueries({ queryKey: ['agent-config-schema', agentId] });
    },
    onError: e => toast.error(`保存失败：${(e as Error).message}`),
  });

  if (schemaQ.isLoading || options.length === 0) return null;

  const set = (key: string, v: unknown) => setEdits(prev => ({ ...prev, [key]: v }));

  const submit = () => {
    for (const o of options) {
      if (!o.required) continue;
      const v = effective(o);
      if (v === '' || v == null) {
        toast.error(`「${o.label}」为必填项`);
        return;
      }
    }
    saveMut.mutate();
  };

  return (
    <div className="mt-4 space-y-3 border-t border-stone-200/60 pt-4">
      <div className="flex items-center gap-1.5 text-[12.5px] font-medium text-stone-700">
        <SlidersHorizontal className="h-3.5 w-3.5 text-stone-400" strokeWidth={1.75} />
        参数
        <span className="text-[11px] font-normal text-stone-400">· 运行时进 ctx.config</span>
      </div>

      <div className="space-y-2.5">
        {options.map(o => (
          <div
            key={o.key}
            className="flex items-center justify-between gap-3 rounded-md border border-stone-200/70 bg-white px-3 py-2.5"
          >
            <div className="min-w-0">
              <div className="text-[12.5px] font-medium text-stone-800">
                {o.label}
                <span className="ml-1.5 font-mono text-[10.5px] font-normal text-stone-400">
                  {o.key}
                </span>
                {o.required && <span className="ml-1 text-rose-500">*</span>}
              </div>
            </div>
            <div className="shrink-0">
              {o.type === 'boolean' ? (
                <Switch checked={!!effective(o)} onCheckedChange={v => set(o.key, v)} />
              ) : o.type === 'select' ? (
                <Select value={String(effective(o))} onValueChange={v => set(o.key, v)}>
                  <SelectTrigger className="w-48">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(o.choices ?? []).map(c => (
                      <SelectItem key={c} value={c}>
                        {c}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  className="w-48"
                  type={o.type === 'number' ? 'number' : 'text'}
                  value={String(effective(o) ?? '')}
                  onChange={e =>
                    // number 清空存 ''（提交时删键回落默认），不再 Number('')=0 静默落库
                    set(
                      o.key,
                      o.type === 'number' && e.target.value !== ''
                        ? Number(e.target.value)
                        : e.target.value,
                    )
                  }
                />
              )}
            </div>
          </div>
        ))}
      </div>

      <Button
        onClick={submit}
        disabled={Object.keys(edits).length === 0 || saveMut.isPending}
      >
        <Save className="h-3.5 w-3.5" /> 保存参数
      </Button>
    </div>
  );
};

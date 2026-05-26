/** Agent 关联模型表单 —— 按 @agent 声明的具名模型槽，逐槽绑定一个已配置模型。
 *
 * 仅 agentkit @agent 智能体声明了模型槽；未声明则提示。锁定槽只读。
 * 不依赖 effect 同步：本地只存"编辑覆盖"，生效值 = 覆盖 ?? 服务端 bound_code。
 */
import { useMemo, useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Cpu, Lock, Save } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { agentApi } from '@/system/agents/services/agent';

interface Props {
  agentId: EntityId;
}

const UNBOUND = '__default__'; // Radix Select 不允许空串 value，用哨兵表示"用默认"

export const LinkedModelsForm = ({ agentId }: Props) => {
  const qc = useQueryClient();
  const slotsQ = useQuery({
    queryKey: ['agent-model-slots', agentId],
    queryFn: () => agentApi.modelSlots(agentId),
  });

  // slot 名 -> 编辑后的 code（"" = 解绑）；未编辑的 slot 不在表里
  const [edits, setEdits] = useState<Record<string, string>>({});

  const slots = slotsQ.data?.slots ?? [];
  const models = slotsQ.data?.models ?? [];

  const effective = (name: string, serverCode: string | null): string =>
    name in edits ? edits[name] : (serverCode ?? '');

  const dirty = useMemo(() => {
    return slots.some(s => name2dirty(s.name, s.bound_code, edits));
  }, [slots, edits]);

  const saveMut = useMutation({
    mutationFn: () => {
      const bindings: Record<string, string> = {};
      for (const s of slots) {
        const code = effective(s.name, s.bound_code);
        if (code) bindings[s.name] = code;
      }
      return agentApi.updateModelBindings(agentId, bindings);
    },
    onSuccess: () => {
      setEdits({});
      toast.success('模型绑定已保存');
      qc.invalidateQueries({ queryKey: ['agent-model-slots', agentId] });
    },
    onError: e => toast.error(`保存失败：${(e as Error).message}`),
  });

  if (slotsQ.isLoading) {
    return <div className="py-12 text-center text-[12.5px] text-stone-400">加载中…</div>;
  }

  if (slots.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-stone-200 px-4 py-8 text-center text-[12.5px] text-stone-400">
        该智能体未声明模型槽。
        <div className="mt-1 text-[11.5px] text-stone-400">
          如需按页面切换模型，请在代码用{' '}
          <code className="font-mono">@agent(models=[ModelSlot(...)])</code> 声明。
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="text-[12px] text-stone-500">
        每个模型槽绑定一个已配置模型；留空 = 用槽默认 / 系统默认。运行时{' '}
        <code className="font-mono">ctx.llm(slot)</code> 按此解析。
      </div>

      <div className="space-y-2.5">
        {slots.map(s => {
          const val = effective(s.name, s.bound_code) || UNBOUND;
          return (
            <div
              key={s.name}
              className="flex items-center gap-3 rounded-md border border-stone-200/70 bg-white px-3 py-2.5"
            >
              <Cpu className="h-4 w-4 shrink-0 text-stone-400" strokeWidth={1.75} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 text-[12.5px] font-medium text-stone-800">
                  {s.label}
                  <span className="font-mono text-[10.5px] font-normal text-stone-400">
                    {s.name}
                  </span>
                  {s.optional && (
                    <span className="text-[10.5px] font-normal text-stone-400">· 可选</span>
                  )}
                  {s.locked && (
                    <span className="inline-flex items-center gap-0.5 text-[10.5px] font-normal text-amber-600">
                      <Lock className="h-3 w-3" /> 锁定
                    </span>
                  )}
                </div>
                {s.default && (
                  <div className="mt-0.5 font-mono text-[10.5px] text-stone-400">
                    默认 {s.default}
                  </div>
                )}
              </div>
              <Select
                value={val}
                disabled={s.locked}
                onValueChange={v =>
                  setEdits(prev => ({ ...prev, [s.name]: v === UNBOUND ? '' : v }))
                }
              >
                <SelectTrigger className="w-56">
                  <SelectValue placeholder="用默认" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={UNBOUND}>默认 / 系统默认</SelectItem>
                  {models.map(m => (
                    <SelectItem key={m.code} value={m.code} className="font-mono">
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          );
        })}
      </div>

      <Button onClick={() => saveMut.mutate()} disabled={!dirty || saveMut.isPending}>
        <Save className="h-3.5 w-3.5" /> 保存绑定
      </Button>
    </div>
  );
};

function name2dirty(
  name: string,
  serverCode: string | null,
  edits: Record<string, string>,
): boolean {
  if (!(name in edits)) return false;
  return edits[name] !== (serverCode ?? '');
}

/** Agent 关联工具表单 —— 按 @agent(tools=[...]) 声明的平台工具逐个启停。
 *
 * 仅 agentkit @agent 智能体可声明平台工具；未声明则提示。本地 @tool 由代码控制、
 * 不在此展示。不依赖 effect 同步：本地只存"编辑覆盖"，生效值 = 覆盖 ?? 服务端 enabled。
 */
import { useMemo, useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Save, Wrench } from 'lucide-react';

import { DetailSection } from '@/system/agents/components/detail-section';

import { Button } from '@/core/components/ui/button';
import { Switch } from '@/core/components/ui/switch';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { agentApi } from '@/system/agents/services/agent';

interface Props {
  agentId: EntityId;
}

export const LinkedToolsForm = ({ agentId }: Props) => {
  const qc = useQueryClient();
  const toolsQ = useQuery({
    queryKey: ['agent-tools', agentId],
    queryFn: () => agentApi.tools(agentId),
  });

  // tool_key -> 编辑后的 enabled；未编辑的不在表里
  const [edits, setEdits] = useState<Record<string, boolean>>({});
  const tools = useMemo(() => toolsQ.data?.tools ?? [], [toolsQ.data]);

  const effective = (key: string, serverEnabled: boolean): boolean =>
    key in edits ? edits[key] : serverEnabled;

  const dirty = useMemo(
    () => tools.some(t => t.tool_key in edits && edits[t.tool_key] !== t.enabled),
    [tools, edits],
  );

  const saveMut = useMutation({
    mutationFn: () => {
      const enabled = tools
        .filter(t => effective(t.tool_key, t.enabled))
        .map(t => t.tool_key);
      return agentApi.updateTools(agentId, enabled);
    },
    onSuccess: () => {
      setEdits({});
      toast.success('工具启停已保存');
      qc.invalidateQueries({ queryKey: ['agent-tools', agentId] });
    },
    onError: e => toast.error(`保存失败：${(e as Error).message}`),
  });

  if (toolsQ.isLoading) {
    return <div className="py-12 text-center text-[12.5px] text-stone-400">加载中…</div>;
  }

  if (tools.length === 0) {
    return (
      <DetailSection icon={Wrench} title="关联工具" desc="启停该应用声明的平台工具">
        <div className="rounded-lg border border-dashed border-stone-200 px-4 py-8 text-center text-[12.5px] text-stone-400">
          该应用未声明平台工具。
          <div className="mt-1 text-[11.5px] text-stone-400">
            如需在页面启停平台工具，请在代码用{' '}
            <code className="font-mono">@agent(tools=[&quot;http&quot;, ...])</code> 声明；
            代码自定义工具（<code className="font-mono">@tool</code>）随代码生效、不在此管理。
          </div>
        </div>
      </DetailSection>
    );
  }

  return (
    <DetailSection
      icon={Wrench}
      title="关联工具"
      desc="启停该应用声明的平台工具；关闭后本应用的工具循环不会绑定它"
    >
      <div className="space-y-2.5">
        {tools.map(t => {
          const on = effective(t.tool_key, t.enabled);
          return (
            <div
              key={t.tool_key}
              className="flex items-center gap-3 rounded-md border border-stone-200/70 bg-white px-3 py-2.5"
            >
              <Wrench className="h-4 w-4 shrink-0 text-stone-400" strokeWidth={1.75} />
              <div className="min-w-0 flex-1">
                <div className="font-mono text-[12.5px] font-medium text-stone-800">
                  {t.tool_key}
                </div>
                {t.description && (
                  <div className="mt-0.5 text-[11.5px] text-stone-500">{t.description}</div>
                )}
              </div>
              <Switch
                checked={on}
                onCheckedChange={v => setEdits(prev => ({ ...prev, [t.tool_key]: v }))}
              />
            </div>
          );
        })}
      </div>

      <div className="mt-4">
        <Button onClick={() => saveMut.mutate()} disabled={!dirty || saveMut.isPending}>
          <Save className="h-3.5 w-3.5" /> 保存
        </Button>
      </div>
    </DetailSection>
  );
};

/** 应用辅助调用模型 inline 编辑器（agent.default_model_code）
 *
 * 语义：followup / 自动标题 / 摘要等「系统侧辅助调用」用的模型。
 * - source='local'：同时也是业务调用模型
 * - source='graph'：业务调用走画布节点各自绑定的模型；这里只配辅助
 *
 * 复用点：应用详情页 InfoTab、工作流编辑器左侧栏「应用辅助模型」卡。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { toast } from '@/core/lib/toast';
import { agentApi } from '@/system/agents/services/agent';
import type { AgentItem } from '@/system/agents/types/agent';
import { modelApi } from '@/system/models/services/model';

interface Props {
  agent: AgentItem;
  /** 紧凑布局（用于编辑器侧栏；默认展开布局用于详情页） */
  compact?: boolean;
}

export const AgentHelperModelField = ({ agent, compact = false }: Props) => {
  const qc = useQueryClient();
  const modelsQ = useQuery({
    queryKey: ['models', 'chat'],
    queryFn: () => modelApi.list({ kind: 'chat' }),
    staleTime: 60_000,
  });
  const updateMut = useMutation({
    mutationFn: (code: string | null) =>
      agentApi.update(agent.id, { default_model_code: code }),
    onSuccess: () => {
      toast.success('已保存');
      // detail 页缓存
      qc.invalidateQueries({ queryKey: ['agent', String(agent.id)] });
      // graph rail 用的 list 缓存
      qc.invalidateQueries({ queryKey: ['agents', 'graph'] });
    },
    onError: e => toast.error(`保存失败：${(e as Error).message}`),
  });

  const current = agent.default_model_code ?? '';
  const desc = agent.source === 'graph'
    ? '辅助调用（followup / 标题 / 摘要）用此模型；业务调用走画布节点各自绑定的模型'
    : 'followup / 自动标题 / 摘要等辅助调用使用';

  const Trigger = (
    <Select
      value={current || '__none__'}
      onValueChange={v => updateMut.mutate(v === '__none__' ? null : v)}
      disabled={modelsQ.isLoading || updateMut.isPending}
    >
      <SelectTrigger className={compact ? 'h-7 w-full' : 'w-60'}>
        <SelectValue placeholder="未配置" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="__none__">— 未配置（走系统默认）—</SelectItem>
        {(modelsQ.data ?? []).map(m => (
          <SelectItem key={m.id} value={m.code}>
            {m.code}
            {m.provider_code && (
              <span className="ml-2 text-[10.5px] text-stone-400">@{m.provider_code}</span>
            )}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  if (compact) {
    return (
      <div>
        <div className="mb-1 text-[10.5px] leading-tight text-stone-400">{desc}</div>
        {Trigger}
      </div>
    );
  }

  return (
    <div className="col-span-2 rounded-md border border-stone-200/70 bg-white px-3 py-2">
      <div className="mb-1 flex items-center justify-between gap-3">
        <div>
          <div className="text-[11px] text-stone-500">辅助模型 · default_model_code</div>
          <div className="text-[11px] leading-tight text-stone-400">{desc}</div>
        </div>
        {Trigger}
      </div>
    </div>
  );
};

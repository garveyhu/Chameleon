/** 应用详情「监测」tab —— 按 agent_key 聚合的真实调用统计
 *
 * 数据源：GET /v1/admin/agents/{id}/overview（按 call_logs 聚合，trace 根去重）。
 * 时间窗 24h / 7d 切换；指标用全站 StatTile 风格：调用次数 / 成功率 / 总 tokens / 总成本 / 平均时延。
 */
import { useState } from 'react';

import { useQuery } from '@tanstack/react-query';
import { Activity, CheckCircle2, Clock, Coins, Cpu } from 'lucide-react';

import { StatTile } from '@/core/components/ui/stat-tile';
import { cn } from '@/core/lib/cn';
import { formatCost, formatDurationMs, formatPercent, formatTokens } from '@/core/lib/format';
import type { EntityId } from '@/core/types/api';
import { agentApi } from '@/system/agents/services/agent';

interface Props {
  agentId: EntityId;
}

const WINDOWS: { value: number; label: string }[] = [
  { value: 24, label: '近 24 小时' },
  { value: 24 * 7, label: '近 7 天' },
];

export const AgentOverviewTab = ({ agentId }: Props) => {
  const [hours, setHours] = useState(24);

  const q = useQuery({
    queryKey: ['agent-overview', agentId, hours],
    queryFn: () => agentApi.overview(agentId, hours),
  });
  const d = q.data;

  const callsDelta =
    d && d.prev_total_calls > 0
      ? (d.total_calls - d.prev_total_calls) / d.prev_total_calls
      : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-1.5">
        {WINDOWS.map(w => (
          <button
            key={w.value}
            type="button"
            onClick={() => setHours(w.value)}
            className={cn(
              'rounded-md px-3 py-1 text-[12px] font-medium transition',
              hours === w.value
                ? 'bg-stone-900 text-white'
                : 'text-stone-500 hover:bg-stone-100 hover:text-stone-800',
            )}
          >
            {w.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <StatTile
          label="调用次数"
          value={d ? formatTokens(d.total_calls) : '—'}
          icon={Activity}
          delta={callsDelta}
          loading={q.isLoading}
        />
        <StatTile
          label="成功率"
          value={d ? formatPercent(d.success_rate) : '—'}
          icon={CheckCircle2}
          tone="success"
          loading={q.isLoading}
        />
        <StatTile
          label="总 Tokens"
          value={d ? formatTokens(d.total_tokens) : '—'}
          icon={Cpu}
          tone="neutral"
          loading={q.isLoading}
        />
        <StatTile
          label="总成本"
          value={d ? formatCost(d.total_cost_usd) : '—'}
          icon={Coins}
          tone="warning"
          loading={q.isLoading}
        />
        <StatTile
          label="平均时延"
          value={d ? formatDurationMs(d.avg_duration_ms) : '—'}
          icon={Clock}
          tone="neutral"
          loading={q.isLoading}
        />
      </div>

      <p className="text-[11px] text-stone-400">
        统计基于该应用调用账本（trace 根，去除嵌套子节点重复计数）。
      </p>
    </div>
  );
};

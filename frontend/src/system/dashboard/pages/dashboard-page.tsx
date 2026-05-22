/** Dashboard 主页：DateRangePicker + 综合指标 + 时序图 + top agents/apps */

import { useQuery } from '@tanstack/react-query';
import { Activity, Bot, KeySquare, Sparkles, TrendingDown, TrendingUp } from 'lucide-react';
import type { ComponentType } from 'react';
import { useMemo, useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { DateRangePicker, type DateRange } from '@/core/components/common/date-range-picker';
import { PageHeader } from '@/core/components/common/page-header';
import { Spinner } from '@/core/components/common/spinner';
import { Card, CardContent } from '@/core/components/ui/card';
import { cn } from '@/core/lib/cn';
import { formatNumber, formatPercent } from '@/core/lib/format';
import { dashboardApi } from '@/system/dashboard/services/dashboard';
import type { OverviewItem } from '@/system/dashboard/types/dashboard';

interface StatCardProps {
  label: string;
  value: string;
  hint?: string;
  delta?: number | null;
  Icon: ComponentType<{ className?: string }>;
  tone?: 'primary' | 'success' | 'warning' | 'danger';
}

const toneClass: Record<NonNullable<StatCardProps['tone']>, string> = {
  primary: 'bg-primary-50 text-primary-600',
  success: 'bg-emerald-50 text-emerald-600',
  warning: 'bg-amber-50 text-amber-600',
  danger: 'bg-red-50 text-red-600',
};

const StatCard = ({ label, value, hint, delta, Icon, tone = 'primary' }: StatCardProps) => (
  <Card>
    <CardContent className="flex items-start justify-between pt-5">
      <div>
        <div className="text-xs text-stone-500">{label}</div>
        <div className="mt-2 font-mono text-2xl tracking-tight text-stone-900">{value}</div>
        <div className="mt-1 flex items-center gap-2 text-[11px]">
          {hint ? <span className="text-stone-400">{hint}</span> : null}
          {delta !== undefined && delta !== null && Number.isFinite(delta) ? (
            <span
              className={cn(
                'inline-flex items-center gap-0.5 font-medium',
                delta > 0 ? 'text-emerald-600' : delta < 0 ? 'text-red-600' : 'text-stone-400',
              )}
            >
              {delta > 0 ? (
                <TrendingUp className="h-3 w-3" />
              ) : delta < 0 ? (
                <TrendingDown className="h-3 w-3" />
              ) : null}
              {delta > 0 ? '+' : ''}
              {(delta * 100).toFixed(1)}%
            </span>
          ) : null}
        </div>
      </div>
      <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${toneClass[tone]}`}>
        <Icon className="h-5 w-5" />
      </div>
    </CardContent>
  </Card>
);

const defaultRange = (): DateRange => {
  const to = new Date();
  to.setHours(23, 59, 59, 999);
  const from = new Date();
  from.setDate(from.getDate() - 6);
  from.setHours(0, 0, 0, 0);
  return { from, to };
};

export const DashboardPage = () => {
  const [range, setRange] = useState<DateRange>(defaultRange);
  const params = useMemo(
    () => ({ from_ts: range.from.toISOString(), to_ts: range.to.toISOString() }),
    [range],
  );

  const overviewQ = useQuery({
    queryKey: ['dashboard', 'overview', params],
    queryFn: () => dashboardApi.overview(params),
  });
  const tsQ = useQuery({
    queryKey: ['dashboard', 'timeseries', params],
    queryFn: () => dashboardApi.timeseries({ ...params, granularity: 'auto' }),
  });
  const agentsQ = useQuery({
    queryKey: ['dashboard', 'top-agents', params],
    queryFn: () => dashboardApi.topAgents({ ...params, limit: 5 }),
  });
  const appsQ = useQuery({
    queryKey: ['dashboard', 'top-apps', params],
    queryFn: () => dashboardApi.topApps({ ...params, limit: 5 }),
  });

  const o: OverviewItem | undefined = overviewQ.data;
  const delta = (() => {
    if (!o || o.prev_period_calls === undefined || o.total_calls_in_range === undefined) return null;
    if (!o.prev_period_calls) return o.total_calls_in_range > 0 ? 1 : 0;
    return (o.total_calls_in_range - o.prev_period_calls) / o.prev_period_calls;
  })();

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <PageHeader title="Dashboard" description="按所选时间区间综合指标" />
        <DateRangePicker value={range} onChange={setRange} />
      </div>

      <div className="grid grid-cols-4 gap-4">
        <StatCard
          label="区间内调用"
          value={formatNumber(o?.total_calls_in_range ?? o?.total_calls_24h ?? 0)}
          hint={`上一周期 ${formatNumber(o?.prev_period_calls ?? 0)}`}
          delta={delta}
          Icon={Activity}
          tone="primary"
        />
        <StatCard
          label="成功率 (24h)"
          value={formatPercent(o?.success_rate_24h ?? 1)}
          hint={`平均 ${(o?.avg_duration_ms_24h ?? 0).toFixed(0)} ms`}
          Icon={Sparkles}
          tone={
            (o?.success_rate_24h ?? 1) > 0.95
              ? 'success'
              : (o?.success_rate_24h ?? 1) > 0.8
                ? 'warning'
                : 'danger'
          }
        />
        <StatCard
          label="Token 消耗 (24h)"
          value={formatNumber(
            (o?.total_prompt_tokens_24h ?? 0) + (o?.total_completion_tokens_24h ?? 0),
          )}
          hint={`提示 ${formatNumber(o?.total_prompt_tokens_24h ?? 0)} · 完成 ${formatNumber(o?.total_completion_tokens_24h ?? 0)}`}
          Icon={Bot}
          tone="primary"
        />
        <StatCard
          label="活跃应用 (24h)"
          value={formatNumber(o?.active_apps_24h ?? 0)}
          hint={`活跃 agent ${o?.active_agents_24h ?? 0}`}
          Icon={KeySquare}
          tone="primary"
        />
      </div>

      <div className="mt-6 grid grid-cols-3 gap-4">
        <Card className="col-span-2">
          <CardContent className="pt-5">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-medium text-stone-900">调用趋势</h3>
              <div className="flex items-center gap-2 text-[11px] text-stone-400">
                {tsQ.data?.granularity ? <span>按 {tsQ.data.granularity}</span> : null}
                {tsQ.isLoading && <Spinner size="sm" />}
              </div>
            </div>
            <div className="h-64">
              {tsQ.data && tsQ.data.points.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={tsQ.data.points}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgb(0 0 0 / 6%)" />
                    <XAxis
                      dataKey="ts"
                      tickFormatter={t =>
                        tsQ.data?.granularity === 'day'
                          ? new Date(t).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
                          : new Date(t).toLocaleTimeString('zh-CN', { hour: '2-digit' })
                      }
                      stroke="#999"
                      fontSize={11}
                    />
                    <YAxis stroke="#999" fontSize={11} />
                    <Tooltip
                      labelFormatter={t => new Date(t as string).toLocaleString('zh-CN')}
                      contentStyle={{
                        background: 'var(--color-paper)',
                        border: '1px solid rgb(0 0 0 / 10%)',
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="total"
                      stroke="var(--color-primary-600)"
                      strokeWidth={2}
                      name="总调用"
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="errors"
                      stroke="#ef4444"
                      strokeWidth={2}
                      name="错误数"
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-stone-400">
                  暂无数据
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-5">
            <h3 className="mb-3 text-sm font-medium text-stone-900">Top Agents</h3>
            <ul className="space-y-2">
              {(agentsQ.data || []).map(a => (
                <li key={a.agent_key} className="flex items-center justify-between text-sm">
                  <span className="font-mono text-stone-700">{a.agent_key}</span>
                  <span className="text-stone-500">{formatNumber(a.count)}</span>
                </li>
              ))}
              {agentsQ.data?.length === 0 && (
                <li className="py-4 text-center text-xs text-stone-400">暂无数据</li>
              )}
            </ul>
          </CardContent>
        </Card>
      </div>

      <div className="mt-4">
        <Card>
          <CardContent className="pt-5">
            <h3 className="mb-3 text-sm font-medium text-stone-900">Top Apps</h3>
            <ul className="space-y-2">
              {(appsQ.data || []).map(a => (
                <li key={a.app_id} className="flex items-center justify-between text-sm">
                  <span className="font-mono text-stone-700">{a.app_id}</span>
                  <span className="text-stone-500">{formatNumber(a.count)}</span>
                </li>
              ))}
              {appsQ.data?.length === 0 && (
                <li className="py-4 text-center text-xs text-stone-400">暂无数据</li>
              )}
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

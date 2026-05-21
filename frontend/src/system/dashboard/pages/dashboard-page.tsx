/** Dashboard 主页：综合指标 + 时序图 + top agents/apps */

import { useQuery } from '@tanstack/react-query';
import { Activity, Bot, KeySquare, Sparkles } from 'lucide-react';
import type { ComponentType } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { PageHeader } from '@/core/components/common/page-header';
import { Spinner } from '@/core/components/common/spinner';
import { Card, CardContent } from '@/core/components/ui/card';
import { formatNumber, formatPercent } from '@/core/lib/format';
import { dashboardApi } from '@/system/dashboard/services/dashboard';
import type { OverviewItem } from '@/system/dashboard/types/dashboard';

interface StatCardProps {
  label: string;
  value: string;
  hint?: string;
  Icon: ComponentType<{ className?: string }>;
  tone?: 'primary' | 'success' | 'warning' | 'danger';
}

const toneClass: Record<NonNullable<StatCardProps['tone']>, string> = {
  primary: 'bg-primary-50 text-primary-600',
  success: 'bg-emerald-50 text-emerald-600',
  warning: 'bg-amber-50 text-amber-600',
  danger: 'bg-red-50 text-red-600',
};

const StatCard = ({ label, value, hint, Icon, tone = 'primary' }: StatCardProps) => (
  <Card>
    <CardContent className="flex items-start justify-between pt-5">
      <div>
        <div className="text-xs text-stone-500">{label}</div>
        <div className="mt-2 font-mono text-2xl tracking-tight text-stone-900">{value}</div>
        {hint && <div className="mt-1 text-[11px] text-stone-400">{hint}</div>}
      </div>
      <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${toneClass[tone]}`}>
        <Icon className="h-5 w-5" />
      </div>
    </CardContent>
  </Card>
);

export const DashboardPage = () => {
  const overviewQ = useQuery({
    queryKey: ['dashboard', 'overview'],
    queryFn: dashboardApi.overview,
  });
  const tsQ = useQuery({
    queryKey: ['dashboard', 'timeseries', 'hour', 24],
    queryFn: () => dashboardApi.timeseries({ granularity: 'hour', hours: 24 }),
  });
  const agentsQ = useQuery({
    queryKey: ['dashboard', 'top-agents'],
    queryFn: () => dashboardApi.topAgents({ limit: 5, hours: 24 }),
  });
  const appsQ = useQuery({
    queryKey: ['dashboard', 'top-apps'],
    queryFn: () => dashboardApi.topApps({ limit: 5, hours: 24 }),
  });

  const o: OverviewItem | undefined = overviewQ.data;

  return (
    <div>
      <PageHeader title="Dashboard" description="过去 24h 综合指标" />

      <div className="grid grid-cols-4 gap-4">
        <StatCard
          label="今日调用"
          value={formatNumber(o?.total_calls_24h ?? 0)}
          hint={`7 天 ${formatNumber(o?.total_calls_7d ?? 0)}`}
          Icon={Activity}
          tone="primary"
        />
        <StatCard
          label="成功率"
          value={formatPercent(o?.success_rate_24h ?? 1)}
          hint={`平均响应 ${(o?.avg_duration_ms_24h ?? 0).toFixed(0)} ms`}
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
          label="Token 消耗"
          value={formatNumber(
            (o?.total_prompt_tokens_24h ?? 0) + (o?.total_completion_tokens_24h ?? 0),
          )}
          hint={`提示 ${formatNumber(o?.total_prompt_tokens_24h ?? 0)} · 完成 ${formatNumber(o?.total_completion_tokens_24h ?? 0)}`}
          Icon={Bot}
          tone="primary"
        />
        <StatCard
          label="活跃应用"
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
              <h3 className="text-sm font-medium text-stone-900">24 小时调用趋势</h3>
              {tsQ.isLoading && <Spinner size="sm" />}
            </div>
            <div className="h-64">
              {tsQ.data && tsQ.data.points.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={tsQ.data.points}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgb(0 0 0 / 6%)" />
                    <XAxis
                      dataKey="ts"
                      tickFormatter={t =>
                        new Date(t).toLocaleTimeString('zh-CN', { hour: '2-digit' })
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

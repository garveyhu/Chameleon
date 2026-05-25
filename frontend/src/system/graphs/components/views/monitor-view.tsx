/** 监测视图 —— 基于真实 graph_runs 的运行指标
 *
 * 不造假数据：总运行数 / 成功率 / 平均耗时 / 失败数，均由 listRuns 聚合；
 * 每日运行次数走 TimeSeriesChart（近 7 天）。
 */
import { useMemo } from 'react';

import { useQuery } from '@tanstack/react-query';
import { Activity, CheckCircle2, Clock, ListChecks } from 'lucide-react';

import { StatTile } from '@/core/components/ui/stat-tile';
import { TimeSeriesChart } from '@/core/components/ui/time-series-chart';
import type { EntityId } from '@/core/types/api';
import { graphApi } from '@/system/graphs/services/graph';

interface Props {
  graphId: EntityId;
}

export const MonitorView = ({ graphId }: Props) => {
  // 取较多近期记录算指标；总运行数用 PageResult.total（全量）
  const q = useQuery({
    queryKey: ['graph-run-metrics', graphId],
    queryFn: () => graphApi.listRuns(graphId, { page: 1, page_size: 200 }),
  });
  const { total, sampled, successPct, avgMs, failed, daily } = useMemo(() => {
    const runs = q.data?.items ?? [];
    const total = q.data?.total ?? 0;
    const sampled = runs.length;
    const succ = runs.filter(r => r.status === 'success').length;
    const failed = runs.filter(r => r.status === 'failed').length;
    const durs = runs.map(r => r.duration_ms).filter((d): d is number => d != null);
    const avgMs = durs.length ? Math.round(durs.reduce((a, b) => a + b, 0) / durs.length) : 0;

    const counts = new Map<string, number>();
    for (const r of runs) {
      const day = r.created_at.slice(0, 10);
      counts.set(day, (counts.get(day) ?? 0) + 1);
    }
    const daily: { date: string; runs: number }[] = [];
    const today = new Date();
    for (let i = 6; i >= 0; i--) {
      const dt = new Date(today);
      dt.setDate(today.getDate() - i);
      const key = dt.toISOString().slice(0, 10);
      daily.push({ date: key.slice(5), runs: counts.get(key) ?? 0 });
    }

    return {
      total,
      sampled,
      successPct: sampled ? Math.round((succ / sampled) * 100) : 0,
      avgMs,
      failed,
      daily,
    };
  }, [q.data]);

  return (
    <div className="h-full overflow-y-auto">
      <div className="px-10 py-8">
        <header className="mb-4 flex items-center gap-2">
          <Activity className="h-4 w-4 text-stone-500" />
          <h1 className="text-[16px] font-semibold text-stone-900">监测</h1>
          <span className="text-[12px] text-stone-400">
            共 {total} 次{sampled < total ? ` · 指标基于最近 ${sampled} 次` : ''}
          </span>
        </header>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatTile
            label="总运行数"
            value={String(total)}
            icon={ListChecks}
            loading={q.isLoading}
          />
          <StatTile
            label="成功率"
            value={`${successPct}%`}
            icon={CheckCircle2}
            loading={q.isLoading}
          />
          <StatTile label="平均耗时" value={`${avgMs}ms`} icon={Clock} loading={q.isLoading} />
          <StatTile label="失败数" value={String(failed)} icon={Activity} loading={q.isLoading} />
        </div>

        <div className="mt-5 rounded-xl border border-stone-200 bg-white p-4">
          <div className="mb-3 text-[13px] font-medium text-stone-800">每日运行次数（近 7 天）</div>
          <TimeSeriesChart
            data={daily}
            xKey="date"
            series={[{ dataKey: 'runs', name: '运行次数', color: '#6366f1' }]}
            height={240}
          />
        </div>
      </div>
    </div>
  );
};

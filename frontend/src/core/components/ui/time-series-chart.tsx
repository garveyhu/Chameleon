/** TimeSeriesChart —— recharts 折线时序图的统一封装。
 *
 * 统一 dashboard / cost 等页面此前各自内联的 LineChart：主题化网格 / 坐标轴 /
 * tooltip，多条 series。空态由 empty 兜底。
 */

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { ReactNode } from 'react';

export interface ChartSeries {
  dataKey: string;
  name: string;
  /** 线条颜色，传 CSS 变量或主题色，如 'var(--color-primary-600)' */
  color: string;
}

interface TimeSeriesChartProps {
  data: Record<string, unknown>[];
  xKey: string;
  series: ChartSeries[];
  height?: number;
  xTickFormatter?: (v: string) => string;
  labelFormatter?: (v: string) => string;
  empty?: ReactNode;
}

export const TimeSeriesChart = ({
  data,
  xKey,
  series,
  height = 256,
  xTickFormatter,
  labelFormatter,
  empty = '暂无数据',
}: TimeSeriesChartProps) => {
  if (!data || data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-sm text-stone-400"
        style={{ height }}
      >
        {empty}
      </div>
    );
  }

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgb(0 0 0 / 6%)" />
          <XAxis dataKey={xKey} tickFormatter={xTickFormatter} stroke="#999" fontSize={11} />
          <YAxis stroke="#999" fontSize={11} />
          <Tooltip
            labelFormatter={labelFormatter}
            contentStyle={{
              background: 'var(--color-paper)',
              border: '1px solid rgb(0 0 0 / 10%)',
              borderRadius: 8,
              fontSize: 12,
            }}
          />
          {series.map(s => (
            <Line
              key={s.dataKey}
              type="monotone"
              dataKey={s.dataKey}
              name={s.name}
              stroke={s.color}
              strokeWidth={2}
              dot={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

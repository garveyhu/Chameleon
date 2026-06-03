/** TimeSeriesChart —— recharts 折线时序图的统一封装。
 *
 * 统一 dashboard / cost 等页面此前各自内联的 LineChart：主题化网格 / 坐标轴 /
 * tooltip，多条 series。空态由 empty 兜底。
 *
 * 双轴：series 标 axis='right' 即叠加右 Y 轴（量纲差异大的指标同图，如成本 + token）；
 * 不传 axis 时为单轴，向后兼容既有调用。
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
  /** 绑左轴（默认）还是右轴（双轴叠加量纲差异大的指标，如成本 + token） */
  axis?: 'left' | 'right';
}

interface TimeSeriesChartProps {
  /** 每个点是一个对象，key 对应 xKey / series.dataKey；类型放宽以兼容各页 DTO */
  data: readonly unknown[];
  xKey: string;
  series: ChartSeries[];
  height?: number;
  xTickFormatter?: (v: string) => string;
  labelFormatter?: (v: string) => string;
  /** 右轴刻度格式化（仅当存在 series.axis==='right'） */
  rightTickFormatter?: (v: number) => string;
  empty?: ReactNode;
}

export const TimeSeriesChart = ({
  data,
  xKey,
  series,
  height = 256,
  xTickFormatter,
  labelFormatter,
  rightTickFormatter,
  empty = '暂无数据',
}: TimeSeriesChartProps) => {
  const hasRight = series.some(s => s.axis === 'right');

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
        <LineChart data={[...data]}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgb(0 0 0 / 6%)" />
          <XAxis
            dataKey={xKey}
            tickFormatter={xTickFormatter}
            stroke="#999"
            fontSize={11}
          />
          <YAxis
            {...(hasRight ? { yAxisId: 'left' } : {})}
            stroke="#999"
            fontSize={11}
          />
          {hasRight && (
            <YAxis
              yAxisId="right"
              orientation="right"
              stroke="#999"
              fontSize={11}
              tickFormatter={rightTickFormatter}
            />
          )}
          <Tooltip
            labelFormatter={
              labelFormatter
                ? (label: unknown) => labelFormatter(String(label))
                : undefined
            }
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
              {...(hasRight
                ? { yAxisId: s.axis === 'right' ? 'right' : 'left' }
                : {})}
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

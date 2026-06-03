/** 分布卡 —— 单维 top-N 横向占比条（渠道 / 错误类型 等）。 */
import { Card, CardContent } from '@/core/components/ui/card';
import { formatNumber } from '@/core/lib/format';
import type { DistributionRow } from '@/system/dashboard/types/dashboard';

interface Props {
  title: string;
  rows: DistributionRow[];
  loading?: boolean;
  empty?: string;
}

export const DistributionCard = ({
  title,
  rows,
  loading,
  empty = '暂无数据',
}: Props) => {
  const total = rows.reduce((s, r) => s + r.count, 0) || 1;
  return (
    <Card>
      <CardContent className="pt-5">
        <h3 className="mb-3 text-sm font-medium text-stone-900">{title}</h3>
        {loading ? (
          <div className="py-6 text-center text-xs text-stone-400">加载中…</div>
        ) : rows.length === 0 ? (
          <div className="py-6 text-center text-xs text-stone-400">{empty}</div>
        ) : (
          <ul className="space-y-2.5">
            {rows.map(r => (
              <li key={r.label}>
                <div className="mb-1 flex items-center justify-between text-[12px]">
                  <span className="truncate text-stone-700">
                    {r.display_name ?? r.label}
                  </span>
                  <span className="tnum shrink-0 pl-2 text-stone-500">
                    {formatNumber(r.count)}
                    <span className="ml-1 text-stone-400">
                      {((r.count / total) * 100).toFixed(0)}%
                    </span>
                  </span>
                </div>
                <div className="relative h-1.5 w-full overflow-hidden rounded bg-stone-100">
                  <div
                    className="bg-primary-400 absolute inset-y-0 left-0 rounded"
                    style={{ width: `${(r.count / total) * 100}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
};

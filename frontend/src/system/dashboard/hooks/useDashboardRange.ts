import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { DateRange } from '@/core/components/common/date-range-picker';

/** 默认区间：近 7 天 */
const defaultRange = (): DateRange => {
  const to = new Date();
  to.setHours(23, 59, 59, 999);
  const from = new Date();
  from.setDate(from.getDate() - 6);
  from.setHours(0, 0, 0, 0);
  return { from, to };
};

/** 时间区间托管在 URL searchParam（?from=&to=）：切 tab / 刷新 / 分享都保留同一口径。
 *  返回 range（给 DateRangePicker）、setRange、params（给后端 from_ts/to_ts）。 */
export function useDashboardRange() {
  const [sp, setSp] = useSearchParams();

  const range = useMemo<DateRange>(() => {
    const f = sp.get('from');
    const t = sp.get('to');
    if (f && t) {
      const from = new Date(f);
      const to = new Date(t);
      if (!Number.isNaN(+from) && !Number.isNaN(+to)) return { from, to };
    }
    return defaultRange();
  }, [sp]);

  const setRange = useCallback(
    (r: DateRange) => {
      setSp(
        prev => {
          const next = new URLSearchParams(prev);
          next.set('from', r.from.toISOString());
          next.set('to', r.to.toISOString());
          return next;
        },
        { replace: true },
      );
    },
    [setSp],
  );

  const params = useMemo(
    () => ({
      from_ts: range.from.toISOString(),
      to_ts: range.to.toISOString(),
    }),
    [range],
  );

  return { range, setRange, params };
}

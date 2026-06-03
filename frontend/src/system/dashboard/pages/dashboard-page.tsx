/** 可观测总览 —— 单页多 tab（概览 / 成本），统一区间联动。
 *
 * 无大标题：tab 栏 + 时间选择器一行。nav 只保留「仪表盘」一个入口（dashboard:read），
 * 成本 tab 在页内按 call_logs:read 权限显隐；两路由 /dashboard、/dashboard/cost 渲染同一壳。
 */
import { useLocation, useNavigate } from 'react-router-dom';

import { DateRangePicker } from '@/core/components/common/date-range-picker';
import { RequirePermission } from '@/core/components/common/permission-guard';
import { cn } from '@/core/lib/cn';
import { useAuthStore } from '@/core/stores/auth-store';
import { useDashboardRange } from '@/system/dashboard/hooks/useDashboardRange';
import { CostTab } from '@/system/dashboard/pages/tabs/cost-tab';
import { OverviewTab } from '@/system/dashboard/pages/tabs/overview-tab';

type TabKey = 'overview' | 'cost';

const TABS: { key: TabKey; label: string; perm: string; path: string }[] = [
  { key: 'overview', label: '概览', perm: 'dashboard:read', path: '/dashboard' },
  { key: 'cost', label: '成本', perm: 'call_logs:read', path: '/dashboard/cost' },
];

export const DashboardPage = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const hasPermission = useAuthStore(s => s.hasPermission);
  const { range, setRange, params } = useDashboardRange();

  const visibleTabs = TABS.filter(t => hasPermission(t.perm));
  const active: TabKey = location.pathname.startsWith('/dashboard/cost')
    ? 'cost'
    : 'overview';
  const activePerm = TABS.find(t => t.key === active)?.perm ?? 'dashboard:read';

  const switchTab = (t: TabKey) => {
    const path = TABS.find(x => x.key === t)?.path;
    if (path && path !== location.pathname) {
      navigate({ pathname: path, search: location.search });
    }
  };

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3">
        {visibleTabs.length > 1 ? (
          <div className="inline-flex gap-1 rounded-lg border border-stone-200 bg-white p-0.5">
            {visibleTabs.map(t => (
              <button
                key={t.key}
                type="button"
                onClick={() => switchTab(t.key)}
                className={cn(
                  'rounded-md px-3.5 py-1 text-[13px] transition',
                  active === t.key
                    ? 'bg-stone-800 text-white'
                    : 'text-stone-600 hover:bg-stone-100',
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
        ) : (
          <div />
        )}
        <DateRangePicker value={range} onChange={setRange} />
      </div>

      <RequirePermission perm={activePerm}>
        {active === 'cost' ? (
          <CostTab params={params} />
        ) : (
          <OverviewTab params={params} />
        )}
      </RequirePermission>
    </div>
  );
};

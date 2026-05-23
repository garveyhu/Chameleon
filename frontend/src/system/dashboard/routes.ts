import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'dashboard',
  parentPath: '/',
  order: 10,
  routes: [
    {
      path: '/dashboard',
      lazy: async () => {
        const m = await import('@/system/dashboard/pages/dashboard-page');
        return { Component: m.DashboardPage };
      },
    },
    {
      path: '/dashboard/cost',
      lazy: async () => {
        const m = await import(
          '@/system/dashboard/pages/cost-dashboard-page'
        );
        return { Component: m.CostDashboardPage };
      },
    },
  ],
};

export default module;

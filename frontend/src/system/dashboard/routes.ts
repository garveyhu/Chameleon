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
  ],
};

export default module;

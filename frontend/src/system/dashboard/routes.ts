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
      // 成本 tab：渲染同一个总览壳，按 pathname 默认切成本 tab（保留路由维持 nav 高亮/权限）
      path: '/dashboard/cost',
      lazy: async () => {
        const m = await import('@/system/dashboard/pages/dashboard-page');
        return { Component: m.DashboardPage };
      },
    },
  ],
};

export default module;

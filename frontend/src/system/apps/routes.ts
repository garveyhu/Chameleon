import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'apps',
  parentPath: '/',
  order: 50,
  routes: [
    {
      path: '/apps',
      lazy: async () => {
        const m = await import('@/system/apps/pages/apps-page');
        return { Component: m.AppsPage };
      },
    },
  ],
};

export default module;

import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'providers',
  parentPath: '/',
  order: 30,
  routes: [
    {
      path: '/providers',
      lazy: async () => {
        const m = await import('@/system/providers/pages/providers-page');
        return { Component: m.ProvidersPage };
      },
    },
  ],
};

export default module;

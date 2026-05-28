import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'api_keys',
  parentPath: '/',
  order: 50,
  routes: [
    {
      path: '/api-keys',
      lazy: async () => {
        const m = await import('@/system/api_keys/pages/apps-page');
        return { Component: m.AppsPage };
      },
    },
  ],
};

export default module;

import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'playground',
  parentPath: '/',
  order: 50,
  routes: [
    {
      path: '/playground',
      lazy: async () => {
        const m = await import('@/system/playground/pages/playground-page');
        return { Component: m.PlaygroundPage };
      },
    },
  ],
};

export default module;

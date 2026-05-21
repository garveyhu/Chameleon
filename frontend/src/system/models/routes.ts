import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'models',
  parentPath: '/',
  order: 35,
  routes: [
    {
      path: '/models',
      lazy: async () => {
        const m = await import('@/system/models/pages/models-page');
        return { Component: m.ModelsPage };
      },
    },
  ],
};

export default module;

import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'abilities',
  parentPath: '/',
  order: 36, // 排在 channels (35) 后面
  routes: [
    {
      path: '/abilities',
      lazy: async () => {
        const m = await import('@/system/abilities/pages/abilities-page');
        return { Component: m.AbilitiesPage };
      },
    },
  ],
};

export default module;

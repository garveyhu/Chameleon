import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'kbs',
  parentPath: '/',
  order: 40,
  routes: [
    {
      path: '/kbs',
      lazy: async () => {
        const m = await import('@/system/kbs/pages/kbs-page');
        return { Component: m.KbsPage };
      },
    },
  ],
};

export default module;

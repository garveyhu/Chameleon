import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'roles',
  parentPath: '/',
  order: 110,
  routes: [
    {
      path: '/roles',
      lazy: async () => {
        const m = await import('@/system/roles/pages/roles-page');
        return { Component: m.RolesPage };
      },
    },
  ],
};

export default module;

import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'users',
  parentPath: '/',
  order: 100,
  routes: [
    {
      path: '/users',
      lazy: async () => {
        const m = await import('@/system/users/pages/users-page');
        return { Component: m.UsersPage };
      },
    },
  ],
};

export default module;

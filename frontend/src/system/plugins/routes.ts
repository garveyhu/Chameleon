import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'plugins',
  parentPath: '/',
  order: 26,
  routes: [
    {
      path: '/plugins',
      lazy: async () => {
        const m = await import('@/system/plugins/pages/plugins-page');
        return { Component: m.PluginsPage };
      },
    },
  ],
};

export default module;

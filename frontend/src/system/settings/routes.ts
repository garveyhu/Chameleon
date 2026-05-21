import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'settings',
  parentPath: '/',
  order: 90,
  routes: [
    {
      path: '/settings',
      lazy: async () => {
        const m = await import('@/system/settings/pages/settings-page');
        return { Component: m.SettingsPage };
      },
    },
  ],
};

export default module;

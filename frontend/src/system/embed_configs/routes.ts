import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'embed_configs',
  parentPath: '/',
  order: 45,
  routes: [
    {
      path: '/embed-configs',
      lazy: async () => {
        const m = await import('@/system/embed_configs/pages/embed-configs-page');
        return { Component: m.EmbedConfigsPage };
      },
    },
  ],
};

export default module;

import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'embed_iframe',
  parentPath: '__root__', // 独立无 layout
  order: 100,
  routes: [
    {
      path: '/embed/:embedKey',
      lazy: async () => {
        const m = await import('@/system/embed_iframe/pages/embed-iframe-page');
        return { Component: m.EmbedIframePage };
      },
    },
  ],
};

export default module;

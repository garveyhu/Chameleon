import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'marketplace',
  parentPath: '/',
  order: 27,
  routes: [
    {
      path: '/marketplace',
      lazy: async () => {
        const m = await import('@/system/marketplace/pages/marketplace-page');
        return { Component: m.MarketplacePage };
      },
    },
    {
      path: '/marketplace/templates',
      lazy: async () => {
        const m = await import(
          '@/system/marketplace/pages/template-gallery-page'
        );
        return { Component: m.TemplateGalleryPage };
      },
    },
  ],
};

export default module;

import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'pricing',
  parentPath: '/',
  order: 36,
  routes: [
    {
      path: '/pricing',
      lazy: async () => {
        const m = await import('@/system/pricing/pages/pricing-page');
        return { Component: m.PricingPage };
      },
    },
  ],
};

export default module;

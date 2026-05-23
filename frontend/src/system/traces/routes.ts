import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'traces',
  parentPath: '/',
  order: 30,
  routes: [
    {
      path: '/traces/:requestId',
      lazy: async () => {
        const m = await import('@/system/traces/pages/trace-detail-page');
        return { Component: m.TraceDetailPage };
      },
    },
  ],
};

export default module;

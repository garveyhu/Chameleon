import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'datasets',
  parentPath: '/',
  order: 27,
  routes: [
    {
      path: '/datasets',
      lazy: async () => {
        const m = await import('@/system/datasets/pages/datasets-page');
        return { Component: m.DatasetsPage };
      },
    },
    {
      path: '/datasets/:id',
      lazy: async () => {
        const m = await import(
          '@/system/datasets/pages/dataset-detail-page'
        );
        return { Component: m.DatasetDetailPage };
      },
    },
  ],
};

export default module;

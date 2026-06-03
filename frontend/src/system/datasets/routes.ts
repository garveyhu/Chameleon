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
    {
      path: '/eval-templates',
      lazy: async () => {
        const m = await import(
          '@/system/datasets/pages/eval-templates-page'
        );
        return { Component: m.EvalTemplatesPage };
      },
    },
  ],
};

export default module;

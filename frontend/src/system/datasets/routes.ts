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
      // ⚠️ 静态 compare 段须排在动态 :runId 前，避免被当作 runId 匹配
      path: '/datasets/:id/runs/compare',
      lazy: async () => {
        const m = await import('@/system/datasets/pages/run-compare-page');
        return { Component: m.RunComparePage };
      },
    },
    {
      path: '/datasets/:id/runs/:runId',
      lazy: async () => {
        const m = await import('@/system/datasets/pages/run-detail-page');
        return { Component: m.RunDetailPage };
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

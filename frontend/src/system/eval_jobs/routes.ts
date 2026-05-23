import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'eval_jobs',
  parentPath: '/',
  order: 28,
  routes: [
    {
      path: '/eval-jobs',
      lazy: async () => {
        const m = await import('@/system/eval_jobs/pages/eval-jobs-page');
        return { Component: m.EvalJobsPage };
      },
    },
    {
      path: '/eval-jobs/:id',
      lazy: async () => {
        const m = await import(
          '@/system/eval_jobs/pages/eval-job-detail-page'
        );
        return { Component: m.EvalJobDetailPage };
      },
    },
  ],
};

export default module;

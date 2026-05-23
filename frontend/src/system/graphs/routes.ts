import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'graphs',
  parentPath: '/',
  order: 25,
  routes: [
    {
      path: '/graphs',
      lazy: async () => {
        const m = await import('@/system/graphs/pages/graphs-page');
        return { Component: m.GraphsPage };
      },
    },
    {
      path: '/graphs/:id/edit',
      lazy: async () => {
        const m = await import('@/system/graphs/pages/graph-editor-page');
        return { Component: m.GraphEditorPage };
      },
    },
  ],
};

export default module;

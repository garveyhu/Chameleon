import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'agents',
  parentPath: '/',
  order: 20,
  routes: [
    {
      path: '/agents',
      lazy: async () => {
        const m = await import('@/system/agents/pages/agents-page');
        return { Component: m.AgentsPage };
      },
    },
  ],
};

export default module;

import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'workspaces',
  parentPath: '/',
  order: 90,
  routes: [
    {
      path: '/workspaces',
      lazy: async () => {
        const m = await import('@/system/workspaces/pages/workspaces-page');
        return { Component: m.WorkspacesPage };
      },
    },
    {
      path: '/workspaces/:id/members',
      lazy: async () => {
        const m = await import(
          '@/system/workspaces/pages/workspace-members-page'
        );
        return { Component: m.WorkspaceMembersPage };
      },
    },
  ],
};

export default module;

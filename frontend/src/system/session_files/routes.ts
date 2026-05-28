import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'session-files',
  parentPath: '/',
  order: 32,
  routes: [
    {
      path: '/session-files',
      lazy: async () => {
        const m = await import('@/system/session_files/pages/session-files-page');
        return { Component: m.SessionFilesPage };
      },
    },
  ],
};

export default module;

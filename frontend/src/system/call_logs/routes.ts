import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'call_logs',
  parentPath: '/',
  order: 60,
  routes: [
    {
      path: '/call-logs',
      lazy: async () => {
        const m = await import('@/system/call_logs/pages/call-logs-page');
        return { Component: m.CallLogsPage };
      },
    },
  ],
};

export default module;

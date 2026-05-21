import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'audit_logs',
  parentPath: '/',
  order: 80,
  routes: [
    {
      path: '/audit-logs',
      lazy: async () => {
        const m = await import('@/system/audit_logs/pages/audit-logs-page');
        return { Component: m.AuditLogsPage };
      },
    },
  ],
};

export default module;

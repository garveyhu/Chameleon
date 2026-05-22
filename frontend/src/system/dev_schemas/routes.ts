import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'dev_schemas',
  parentPath: '/',
  order: 990,  // 排到最后
  routes: [
    {
      path: '/dev/schemas',
      lazy: async () => {
        const m = await import('@/system/dev_schemas/pages/dev-schemas-page');
        return { Component: m.DevSchemasPage };
      },
    },
  ],
};

export default module;

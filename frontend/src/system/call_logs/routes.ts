import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'call_logs',
  parentPath: '/',
  order: 60,
  routes: [
    // 会话（thread）列表 —— 按 ChatSession 维度（多轮一条），区别于 /traces（单次运行）
    {
      path: '/sessions',
      lazy: async () => {
        const m = await import('@/system/call_logs/pages/sessions-page');
        return { Component: m.SessionsPage };
      },
    },
  ],
};

export default module;

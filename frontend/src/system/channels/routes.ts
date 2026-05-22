import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'channels',
  parentPath: '/',
  // 排在 providers (30) 后面，模型 (40+) 前面
  order: 35,
  routes: [
    {
      path: '/channels',
      lazy: async () => {
        const m = await import('@/system/channels/pages/channels-page');
        return { Component: m.ChannelsPage };
      },
    },
  ],
};

export default module;

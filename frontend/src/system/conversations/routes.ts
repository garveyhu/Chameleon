import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'conversations',
  parentPath: '/',
  order: 29,
  routes: [
    {
      path: '/conversations/:sessionId',
      lazy: async () => {
        const m = await import(
          '@/system/conversations/pages/conversation-detail-page'
        );
        return { Component: m.ConversationDetailPage };
      },
    },
  ],
};

export default module;

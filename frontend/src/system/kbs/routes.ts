import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'kbs',
  parentPath: '/',
  order: 40,
  routes: [
    {
      path: '/kbs',
      lazy: async () => {
        const m = await import('@/system/kbs/pages/kbs-page');
        return { Component: m.KbsPage };
      },
    },
    {
      path: '/kbs/:id',
      lazy: async () => {
        const m = await import('@/system/kbs/pages/kb-detail-page');
        return { Component: m.KbDetailPage };
      },
    },
    {
      path: '/kbs/:id/documents/:docId',
      lazy: async () => {
        const m = await import('@/system/kbs/pages/kb-document-detail-page');
        return { Component: m.KbDocumentDetailPage };
      },
    },
    {
      path: '/kbs/:id/chunking-preview',
      lazy: async () => {
        const m = await import('@/system/kbs/pages/kb-chunking-preview-page');
        return { Component: m.KbChunkingPreviewPage };
      },
    },
  ],
};

export default module;

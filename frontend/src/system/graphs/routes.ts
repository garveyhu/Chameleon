import type { ModuleRouteConfig } from '@/core/types/router';

/** 工作流列表 —— 挂在后台壳（MainLayout）内 */
const listModule: ModuleRouteConfig = {
  moduleId: 'graphs',
  parentPath: '/',
  order: 25,
  routes: [
    {
      path: '/graphs',
      lazy: async () => {
        const m = await import('@/system/graphs/pages/graphs-page');
        return { Component: m.GraphsPage };
      },
    },
  ],
};

/** 工作流编辑器 —— 脱离后台壳整屏铺满（页面内自带 RequireAuth 守卫） */
export const editorModule: ModuleRouteConfig = {
  moduleId: 'graphs-editor',
  parentPath: '__root__',
  order: 25,
  routes: [
    {
      path: '/graphs/:id/edit',
      lazy: async () => {
        const m = await import('@/system/graphs/pages/graph-editor-page');
        return { Component: m.GraphEditorPage };
      },
    },
  ],
};

export default listModule;

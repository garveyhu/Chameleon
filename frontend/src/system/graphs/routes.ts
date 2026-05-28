import { createElement } from 'react';
import { Navigate } from 'react-router-dom';

import type { ModuleRouteConfig } from '@/core/types/router';

/** /graphs 旧列表入口 —— 工作流已并入「应用」卡片库，重定向过去 */
const listModule: ModuleRouteConfig = {
  moduleId: 'graphs',
  parentPath: '/',
  order: 25,
  routes: [
    {
      path: '/graphs',
      Component: () => createElement(Navigate, { to: '/agents', replace: true }),
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

import { createElement } from 'react';
import { Navigate } from 'react-router-dom';

import type { ModuleRouteConfig } from '@/core/types/router';

/** /embed-configs 旧列表入口 —— 嵌入已并入「应用」卡片操作/详情，重定向到应用库 */
const module: ModuleRouteConfig = {
  moduleId: 'embed_configs',
  parentPath: '/',
  order: 45,
  routes: [
    {
      path: '/embed-configs',
      Component: () => createElement(Navigate, { to: '/agents', replace: true }),
    },
  ],
};

export default module;

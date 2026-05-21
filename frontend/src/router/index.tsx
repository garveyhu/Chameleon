/** 路由表（动态发现）
 *
 * 用 Vite 的 import.meta.glob 扫 src/system 各模块的 routes.ts，
 * 每个 module default-export 一个 ModuleRouteConfig，自动汇总。
 *
 * parentPath 约定：
 *   '/'         挂到 MainLayout 下（默认，绝大多数业务页面）
 *   '__root__'  不要 MainLayout（登录 / 首次改密等独立页）
 */

import { createBrowserRouter, Navigate, type RouteObject } from 'react-router-dom';

import { MainLayout } from '@/core/components/layout/main-layout';
import type { ModuleRouteConfig, RouteConfig } from '@/core/types/router';

const routeModules = import.meta.glob<Record<string, unknown>>(
  '../system/**/routes.ts',
  { eager: true },
);

// 每个 routes.ts 可以 default 也可以 named export 多个 ModuleRouteConfig
// （如 auth 同时挂 __root__ 登录页和 / 改密页）
const modules: ModuleRouteConfig[] = [];
for (const mod of Object.values(routeModules)) {
  for (const exported of Object.values(mod)) {
    if (
      exported &&
      typeof exported === 'object' &&
      'moduleId' in exported &&
      'routes' in exported
    ) {
      modules.push(exported as ModuleRouteConfig);
    }
  }
}
modules.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

const byParent = new Map<string, RouteConfig[]>();
for (const mod of modules) {
  const parent = mod.parentPath ?? '/';
  const arr = byParent.get(parent) || [];
  arr.push(...mod.routes);
  byParent.set(parent, arr);
}

function toRouteObject(rc: RouteConfig): RouteObject {
  const ro: RouteObject = { path: rc.path };
  if (rc.Component) ro.Component = rc.Component;
  if (rc.lazy) ro.lazy = rc.lazy as RouteObject['lazy'];
  if (rc.children) ro.children = rc.children.map(toRouteObject);
  return ro;
}

const layoutChildren = (byParent.get('/') || []).map(toRouteObject);
const rootChildren = (byParent.get('__root__') || []).map(toRouteObject);

export const router = createBrowserRouter([
  ...rootChildren,
  {
    path: '/',
    Component: MainLayout,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      ...layoutChildren,
    ],
  },
  {
    path: '*',
    element: (
      <div className="flex h-screen items-center justify-center text-stone-500">404 Not Found</div>
    ),
  },
]);

/** 路由配置类型（与 sage 风格对齐） */

import type { ComponentType } from 'react';
import type { RouteObject } from 'react-router-dom';

export interface RouteMeta {
  /** 菜单标题（中文） */
  title?: string;
  /** 菜单图标（lucide-react 组件名） */
  icon?: string;
  /** 调用接口所需权限点（require_permission，多个为 and 关系） */
  permissions?: string[];
  /** 角色守卫（多个为 or 关系） */
  roles?: string[];
  /** 是否在侧边栏菜单中显示 */
  hideInMenu?: boolean;
  /** 菜单排序权重（小的靠前） */
  order?: number;
  /** 父菜单分组（顶级菜单 group 字段） */
  group?: string;
}

export interface RouteConfig extends Omit<RouteObject, 'children' | 'element' | 'Component' | 'lazy'> {
  path: string;
  Component?: ComponentType;
  lazy?: () => Promise<{ Component: ComponentType }>;
  children?: RouteConfig[];
  meta?: RouteMeta;
}

/** 一个 system 模块的路由定义（routes.ts 默认导出） */
export interface ModuleRouteConfig {
  /** 模块 ID（用于 debug / 排序） */
  moduleId: string;
  /** 挂到哪个父路由下（默认 '/'，即 MainLayout 内的二级路由） */
  parentPath?: string;
  /** 排序（小的靠前） */
  order?: number;
  /** 路由表 */
  routes: RouteConfig[];
}

/** 菜单项（Sidebar 渲染用） */
export interface MenuItem {
  path: string;
  title: string;
  icon?: string;
  permissions?: string[];
  roles?: string[];
  group?: string;
  order?: number;
}

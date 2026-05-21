import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'auth',
  parentPath: '__root__', // 不要 MainLayout（独立全屏页）
  order: 0,
  routes: [
    {
      path: '/login',
      lazy: async () => {
        const m = await import('@/system/auth/pages/login-page');
        return { Component: m.LoginPage };
      },
    },
    {
      path: '/first-change-password',
      lazy: async () => {
        const m = await import('@/system/auth/pages/first-password-page');
        return { Component: m.FirstPasswordPage };
      },
    },
  ],
};

export default module;

// 已登录用户改密路由放 MainLayout 下
export const changePasswordRoute: ModuleRouteConfig = {
  moduleId: 'auth-change',
  parentPath: '/',
  routes: [
    {
      path: '/change-password',
      lazy: async () => {
        const m = await import('@/system/auth/pages/change-password-page');
        return { Component: m.ChangePasswordPage };
      },
    },
  ],
};

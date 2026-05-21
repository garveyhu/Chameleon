import { createBrowserRouter, Navigate } from 'react-router-dom';

// 临时占位路由；P8.3 接入动态发现 import.meta.glob 后替换
export const router = createBrowserRouter([
  {
    path: '/',
    element: <Navigate to="/dashboard" replace />,
  },
  {
    path: '/login',
    lazy: async () => {
      const { LoginPage } = await import('@/system/auth/pages/login-page');
      return { Component: LoginPage };
    },
  },
  {
    path: '/dashboard',
    lazy: async () => {
      const { DashboardPage } = await import('@/system/dashboard/pages/dashboard-page');
      return { Component: DashboardPage };
    },
  },
  {
    path: '*',
    element: <div className="flex h-screen items-center justify-center text-stone-500">404</div>,
  },
]);

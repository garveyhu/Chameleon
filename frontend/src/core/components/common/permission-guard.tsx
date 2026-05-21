/** 路由 / 组件级权限守卫
 *
 * 用法：
 *   <RequireAuth>            登录则放行；未登录跳 /login
 *   <RequirePermission perm="users:write">  缺权限显示 403
 */

import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { useAuthStore } from '@/core/stores/auth-store';

export const RequireAuth = ({ children }: { children: ReactNode }) => {
  const isAuthenticated = useAuthStore(s => s.isAuthenticated);
  const user = useAuthStore(s => s.user);
  const location = useLocation();

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  // 首次登录强制改密
  if (user.must_change_password && location.pathname !== '/first-change-password') {
    return <Navigate to="/first-change-password" replace />;
  }
  return <>{children}</>;
};

interface RequirePermissionProps {
  perm: string | string[];
  children: ReactNode;
  fallback?: ReactNode;
}

export const RequirePermission = ({ perm, children, fallback }: RequirePermissionProps) => {
  const hasPermission = useAuthStore(s => s.hasPermission);
  const perms = Array.isArray(perm) ? perm : [perm];
  const ok = perms.every(p => hasPermission(p));

  if (!ok) {
    return (
      <>{fallback ?? <div className="p-8 text-center text-stone-500">权限不足（{perms.join(', ')}）</div>}</>
    );
  }
  return <>{children}</>;
};

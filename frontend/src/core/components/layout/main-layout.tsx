/** 主布局 —— waveflow 风格：sidebar + content（无 topbar）
 *
 * 用户菜单 / 语言切换 / 改密 / 登出 都收纳进 sidebar 底部 dropdown。
 * 顶部留给页面 PageHeader 自由发挥。
 */

import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';

import { CommandPalette, pushRecent } from '@/core/components/command/command-palette';
import { NavProgressBar } from '@/core/components/common/nav-progress-bar';
import { RequireAuth } from '@/core/components/common/permission-guard';
import { Sidebar } from '@/core/components/layout/sidebar';

const PATH_LABELS: Record<string, string> = {
  '/dashboard': '仪表盘',
  '/users': '用户管理',
  '/roles': '角色管理',
  '/apps': '应用 API Key',
  '/providers': 'Providers',
  '/models': 'Models',
  '/agents': 'Agents',
  '/kbs': '知识库',
  '/embed-configs': '嵌入配置',
  '/call-logs': 'Trace',
  '/traces': 'Trace',
  '/audit-logs': '审计日志',
  '/settings': '系统设置',
  '/change-password': '修改密码',
};

export const MainLayout = () => {
  // P22.5 PR #84：移动端默认 collapsed（< md 屏幕）；桌面端默认展开
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia('(max-width: 767px)').matches;
  });
  const location = useLocation();

  useEffect(() => {
    const label = PATH_LABELS[location.pathname];
    if (label) pushRecent(location.pathname, label);
  }, [location.pathname]);

  // P22.5：viewport 变化时同步 collapsed
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 767px)');
    const handler = (e: MediaQueryListEvent) => {
      if (e.matches) setCollapsed(true);
    };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  return (
    <RequireAuth>
      <div className="flex h-screen bg-[var(--color-warm)]">
        <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />
        <main className="flex-1 overflow-auto px-3 py-3 md:px-6 md:py-4">
          <Outlet />
        </main>
      </div>
      <CommandPalette />
      <NavProgressBar />
    </RequireAuth>
  );
};

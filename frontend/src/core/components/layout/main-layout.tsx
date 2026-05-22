/** 主布局 —— waveflow 风格：sidebar + content（无 topbar）
 *
 * 用户菜单 / 语言切换 / 改密 / 登出 都收纳进 sidebar 底部 dropdown。
 * 顶部留给页面 PageHeader 自由发挥。
 */

import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';

import { CommandPalette, pushRecent } from '@/core/components/command/command-palette';
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
  '/call-logs': '调用日志',
  '/audit-logs': '审计日志',
  '/settings': '系统设置',
  '/change-password': '修改密码',
};

export const MainLayout = () => {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();

  useEffect(() => {
    const label = PATH_LABELS[location.pathname];
    if (label) pushRecent(location.pathname, label);
  }, [location.pathname]);

  return (
    <RequireAuth>
      <div className="flex h-screen bg-[var(--color-warm)]">
        <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />
        <main className="flex-1 overflow-auto px-6 py-4">
          <Outlet />
        </main>
      </div>
      <CommandPalette />
    </RequireAuth>
  );
};

/** 主布局 —— waveflow 风格：sidebar + content（无 topbar）
 *
 * 用户菜单 / 语言切换 / 改密 / 登出 都收纳进 sidebar 底部 dropdown。
 * 顶部留给页面 PageHeader 自由发挥。
 */

import { useState } from 'react';
import { Outlet } from 'react-router-dom';

import { RequireAuth } from '@/core/components/common/permission-guard';
import { Sidebar } from '@/core/components/layout/sidebar';

export const MainLayout = () => {
  const [collapsed, setCollapsed] = useState(false);
  return (
    <RequireAuth>
      <div className="flex h-screen bg-[var(--color-warm)]">
        <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />
        <main className="flex-1 overflow-auto px-6 py-4">
          <Outlet />
        </main>
      </div>
    </RequireAuth>
  );
};

/** 主布局（侧边栏 + Topbar + content） */

import { useState } from 'react';
import { Outlet } from 'react-router-dom';

import { RequireAuth } from '@/core/components/common/permission-guard';
import { Sidebar } from '@/core/components/layout/sidebar';
import { Topbar } from '@/core/components/layout/topbar';

export const MainLayout = () => {
  const [collapsed, setCollapsed] = useState(false);
  return (
    <RequireAuth>
      <div className="flex h-screen bg-[var(--color-warm)]">
        <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />
        <div className="flex flex-1 flex-col">
          <Topbar />
          <main className="flex-1 overflow-auto p-8">
            <Outlet />
          </main>
        </div>
      </div>
    </RequireAuth>
  );
};

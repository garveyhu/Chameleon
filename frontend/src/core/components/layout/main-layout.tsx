/** 主布局 —— 顶栏(域切换) + 无边二级导航 + 内容，占满整屏 full-bleed
 *
 *   ┌──────────────────────────────────────────┐
 *   │ TopBar  品牌 | 域tabs ……… 搜索 · 账户       │
 *   ├──────────┬───────────────────────────────┤
 *   │ Secondary│  Outlet（页面内容）             │
 *   │   Nav    │                                │
 *   └──────────┴───────────────────────────────┘
 *
 * 账户菜单收纳进 TopBar 右上角；⌘K 命令面板全局可唤起。
 */
import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';

import { CommandPalette, pushRecent } from '@/core/components/command/command-palette';
import { NavProgressBar } from '@/core/components/common/nav-progress-bar';
import { RequireAuth } from '@/core/components/common/permission-guard';
import { SecondaryNav } from '@/core/components/layout/secondary-nav';
import { TopBar } from '@/core/components/layout/top-bar';

const PATH_LABELS: Record<string, string> = {
  '/dashboard': '仪表盘',
  '/agents': '应用',
  '/graphs': '工作流',
  '/playground': '对话 / Playground',
  '/embed-configs': '嵌入式',
  '/providers': 'Providers',
  '/models': '模型',
  '/kbs': '知识库',
  '/sessions': '会话 & 运行',
  '/traces': 'Trace',
  '/datasets': 'Datasets',
  '/eval-jobs': '评测任务',
  '/audit-logs': '审计日志',
  '/api-keys': 'Key 管理',
  '/users': '用户管理',
  '/roles': '角色管理',
  '/settings': '系统配置',
  '/change-password': '修改密码',
};

export const MainLayout = () => {
  const location = useLocation();

  useEffect(() => {
    const label = PATH_LABELS[location.pathname];
    if (label) pushRecent(location.pathname, label);
  }, [location.pathname]);

  return (
    <RequireAuth>
      <div className="flex h-screen flex-col bg-[var(--color-warm)]">
        <TopBar />
        <div className="flex min-h-0 flex-1">
          <SecondaryNav />
          <main className="flex-1 overflow-auto px-6 py-4">
            <Outlet />
          </main>
        </div>
      </div>
      <CommandPalette />
      <NavProgressBar />
    </RequireAuth>
  );
};

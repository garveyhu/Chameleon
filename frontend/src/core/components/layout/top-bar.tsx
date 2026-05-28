/** 顶栏 —— 浅通栏 app-shell，域切换左对齐
 *
 *   品牌 | 域 tabs（工作台/知识库/观测/设置）……搜索(⌘K) · 账户
 *
 * 账户菜单（语言 / 改密 / 登出）从旧侧栏底部迁移到此处右上角。
 */
import * as React from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { BookOpen, LogOut, Settings } from 'lucide-react';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/core/components/ui/dropdown-menu';
import { DOMAINS, findActiveDomain, type NavDomain } from '@/core/components/layout/nav-config';
import { cn } from '@/core/lib/cn';
import { useAuthStore } from '@/core/stores/auth-store';

export const TopBar = () => {
  const { pathname } = useLocation();
  const { t } = useTranslation();
  const hasPermission = useAuthStore(s => s.hasPermission);
  const [hydrated, setHydrated] = React.useState(false);
  // 权限就绪后再过滤域（避免首屏闪烁）；有意的 effect setState
  // eslint-disable-next-line react-hooks/set-state-in-effect
  React.useEffect(() => setHydrated(true), []);

  const domainVisible = (d: NavDomain) =>
    !hydrated || d.groups.some(g => g.children.some(l => !l.perm || hasPermission(l.perm)));
  const visibleDomains = DOMAINS.filter(domainVisible);
  const activeDomain = findActiveDomain(pathname);

  return (
    <header className="flex h-14 flex-shrink-0 items-center gap-4 border-b border-stone-200/70 bg-[var(--color-paper)] px-4">
      <Link to="/dashboard" className="flex items-center gap-2.5">
        <img src="/logo-sm.png" alt="Chameleon" className="h-7 w-7 flex-shrink-0 object-contain" />
        <span className="text-[15px] font-semibold tracking-tight text-stone-800">Chameleon</span>
      </Link>

      <span className="h-5 w-px bg-stone-200" />

      {/* 域 tabs（左对齐） */}
      <nav className="flex items-center gap-1">
        {visibleDomains.map(d => {
          const Icon = d.icon;
          const active = d.key === activeDomain.key;
          return (
            <Link
              key={d.key}
              to={d.to}
              className={cn(
                'flex items-center gap-2 rounded-[10px] px-3.5 py-2 text-[13.5px] font-semibold transition',
                active
                  ? 'bg-blue-50 text-blue-700'
                  : 'text-stone-600 hover:bg-stone-100/70 hover:text-stone-900',
              )}
            >
              <Icon className={cn('h-[17px] w-[17px]', active ? 'text-blue-600' : 'text-stone-400')} />
              {t(d.i18nKey, d.fallbackTitle)}
            </Link>
          );
        })}
      </nav>

      {/* 右侧：账户 */}
      <div className="ml-auto flex items-center">
        <AccountMenu />
      </div>
    </header>
  );
};

// ── 账户菜单（迁移自旧侧栏底部）────────────────────────────
const AccountMenu = () => {
  const user = useAuthStore(s => s.user);
  const logout = useAuthStore(s => s.logout);
  const navigate = useNavigate();
  const { t } = useTranslation();

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  const username = user?.display_name || user?.username || '—';
  const email = user?.email || '';

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          title={t('topbar.account', '账户菜单')}
          className="rounded-full outline-none transition hover:brightness-105 focus-visible:ring-2 focus-visible:ring-blue-500/40"
        >
          <img
            src="/default-avatar.jpg"
            alt={username}
            className="h-8 w-8 rounded-full object-cover"
          />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        side="bottom"
        sideOffset={8}
        className="w-64 rounded-xl border-stone-200/80 p-1.5 shadow-[var(--shadow-pop)]"
      >
        {/* 用户头部 */}
        <div className="flex items-center gap-3 px-2.5 py-2.5">
          <img
            src="/default-avatar.jpg"
            alt={username}
            className="h-9 w-9 flex-shrink-0 rounded-full object-cover"
          />
          <div className="min-w-0">
            <div className="truncate text-[13.5px] font-semibold text-stone-800">{username}</div>
            {email && <div className="truncate text-[11.5px] text-stone-400">{email}</div>}
          </div>
        </div>
        <DropdownMenuSeparator className="bg-stone-200/60" />
        <DropdownMenuItem
          onClick={() => navigate('/api-docs')}
          className="gap-2.5 rounded-lg px-2.5 py-2 text-[13px]"
        >
          <BookOpen className="h-4 w-4 text-stone-400" />
          {t('menu.apiDocs', 'API 文档')}
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => navigate('/settings')}
          className="gap-2.5 rounded-lg px-2.5 py-2 text-[13px]"
        >
          <Settings className="h-4 w-4 text-stone-400" />
          {t('menu.settings', '系统配置')}
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={handleLogout}
          className="gap-2.5 rounded-lg px-2.5 py-2 text-[13px] text-red-600 hover:bg-red-50 focus:bg-red-50"
        >
          <LogOut className="h-4 w-4" /> {t('topbar.logout', '退出登录')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

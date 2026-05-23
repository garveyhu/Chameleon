/** 主侧栏 —— waveflow 风格复刻
 *
 * 分两个状态：
 *   - 展开 (w-60)：暖白基底 + 树形分组菜单 + 底部用户菜单
 *   - 折叠 (w-14)：icon-only + tooltip
 *
 * 设计要点：
 *   - bg: var(--color-warm-2)
 *   - menu item hover/active: bg-paper + shadow-soft
 *   - 子项：tree-line 连接线（CSS class）
 *   - 分组标题：11px UPPERCASE 灰色
 *   - 底部：头像 + 用户名 + dropdown（语言切换 / 改密 / 登出）
 */

import {
  Activity,
  Bot,
  ChevronDown,
  ChevronRight,
  Cpu,
  Database,
  DollarSign,
  FlaskConical,
  Globe,
  KeyRound,
  KeySquare,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  Network,
  Newspaper,
  PanelLeftClose,
  PanelLeftOpen,
  PlaySquare,
  Plug,
  Puzzle,
  Settings,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  Users2,
  Workflow,
} from 'lucide-react';
import type { ComponentType } from 'react';
import * as React from 'react';

import { WorkspaceSwitcher } from '@/system/workspaces/components/workspace-switcher';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/core/components/ui/dropdown-menu';
import { setLanguage } from '@/core/i18n';
import { cn } from '@/core/lib/cn';
import { useAuthStore } from '@/core/stores/auth-store';

interface NavLeaf {
  to: string;
  icon: ComponentType<{ className?: string }>;
  i18nKey: string;
  fallbackTitle: string;
  perm?: string;
  badge?: React.ReactNode;
}

interface NavGroup {
  to: string;
  icon: ComponentType<{ className?: string }>;
  i18nKey: string;
  fallbackTitle: string;
  children: NavLeaf[];
}

// ── 顶部直链 ─────────────────────────────────────────────
const TOP_ITEMS: NavLeaf[] = [
  { to: '/dashboard', icon: LayoutDashboard, i18nKey: 'menu.dashboard', fallbackTitle: '仪表盘', perm: 'dashboard:read' },
  { to: '/dashboard/cost', icon: DollarSign, i18nKey: 'menu.cost', fallbackTitle: '成本统计', perm: 'call_logs:read' },
];

// ── AI 能力分组 ─────────────────────────────────────────
const AI_GROUP: NavGroup = {
  to: '/agents',
  icon: Bot,
  i18nKey: 'menu.group.ai',
  fallbackTitle: 'AI 能力',
  children: [
    { to: '/agents', icon: Bot, i18nKey: 'menu.agents', fallbackTitle: '智能体', perm: 'agents:read' },
    { to: '/providers', icon: Globe, i18nKey: 'menu.providers', fallbackTitle: 'Providers', perm: 'providers:read' },
    { to: '/channels', icon: Plug, i18nKey: 'menu.channels', fallbackTitle: 'Channels', perm: 'channels:read' },
    { to: '/abilities', icon: Network, i18nKey: 'menu.abilities', fallbackTitle: 'Abilities', perm: 'abilities:read' },
    { to: '/models', icon: Sparkles, i18nKey: 'menu.models', fallbackTitle: '模型', perm: 'models:read' },
    { to: '/kbs', icon: Database, i18nKey: 'menu.kbs', fallbackTitle: '知识库', perm: 'kbs:read' },
    { to: '/playground', icon: PlaySquare, i18nKey: 'menu.playground', fallbackTitle: 'Playground', perm: 'playground:invoke' },
    { to: '/conversations', icon: MessageSquare, i18nKey: 'menu.conversations', fallbackTitle: '对话', perm: 'playground:invoke' },
    { to: '/graphs', icon: Workflow, i18nKey: 'menu.graphs', fallbackTitle: '工作流', perm: 'graphs:read' },
    { to: '/datasets', icon: Database, i18nKey: 'menu.datasets', fallbackTitle: 'Datasets', perm: 'datasets:read' },
    { to: '/eval-jobs', icon: FlaskConical, i18nKey: 'menu.eval_jobs', fallbackTitle: '评测任务', perm: 'datasets:read' },
    { to: '/plugins', icon: Puzzle, i18nKey: 'menu.plugins', fallbackTitle: '插件', perm: 'plugins:read' },
    { to: '/marketplace', icon: ShoppingBag, i18nKey: 'menu.marketplace', fallbackTitle: '插件市场', perm: 'plugins:read' },
    { to: '/embed-configs', icon: Cpu, i18nKey: 'menu.embed_configs', fallbackTitle: '嵌入式', perm: 'embed_configs:read' },
  ],
};

// ── 应用 & 调用分组 ─────────────────────────────────────
const ACCESS_GROUP: NavGroup = {
  to: '/apps',
  icon: KeySquare,
  i18nKey: 'menu.group.access',
  fallbackTitle: '应用 & 调用',
  children: [
    { to: '/apps', icon: KeySquare, i18nKey: 'menu.apps', fallbackTitle: '应用 & API Key', perm: 'apps:read' },
    { to: '/call-logs', icon: Activity, i18nKey: 'menu.call_logs', fallbackTitle: '调用日志', perm: 'call_logs:read' },
    { to: '/users', icon: Users2, i18nKey: 'menu.users', fallbackTitle: '用户', perm: 'users:read' },
    { to: '/roles', icon: ShieldCheck, i18nKey: 'menu.roles', fallbackTitle: '角色', perm: 'roles:read' },
  ],
};

// ── 系统直链（去掉关于） ─────────────────────────────────
const SYSTEM_ITEMS: NavLeaf[] = [
  { to: '/audit-logs', icon: Newspaper, i18nKey: 'menu.audit_logs', fallbackTitle: '审计日志', perm: 'audit_logs:read' },
  { to: '/settings', icon: Settings, i18nKey: 'menu.settings', fallbackTitle: '系统配置', perm: 'settings:read' },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export const Sidebar = ({ collapsed, onToggle }: SidebarProps) => {
  const { pathname } = useLocation();
  const hasPermission = useAuthStore(s => s.hasPermission);
  const [hydrated, setHydrated] = React.useState(false);
  React.useEffect(() => setHydrated(true), []);

  const [openGroups, setOpenGroups] = React.useState<Record<string, boolean>>({
    [AI_GROUP.to]: true,
    [ACCESS_GROUP.to]: true,
  });
  const toggleGroup = (key: string) =>
    setOpenGroups(prev => ({ ...prev, [key]: !prev[key] }));

  const visibleLeaves = (items: NavLeaf[]) =>
    items.filter(it => !it.perm || (hydrated && hasPermission(it.perm)));
  const visibleGroup = (g: NavGroup): NavGroup | null => {
    const children = visibleLeaves(g.children);
    return children.length ? { ...g, children } : null;
  };

  const isActive = (to: string) => pathname === to || pathname.startsWith(to + '/');

  if (collapsed) {
    return (
      <CollapsedSidebar
        pathname={pathname}
        onToggle={onToggle}
        visibleTop={visibleLeaves(TOP_ITEMS)}
        visibleAi={visibleGroup(AI_GROUP)}
        visibleAccess={visibleGroup(ACCESS_GROUP)}
        visibleSystem={visibleLeaves(SYSTEM_ITEMS)}
      />
    );
  }

  const visibleAi = visibleGroup(AI_GROUP);
  const visibleAccess = visibleGroup(ACCESS_GROUP);
  const sysVisible = visibleLeaves(SYSTEM_ITEMS);

  return (
    <aside className="flex h-full w-60 flex-shrink-0 flex-col border-r border-stone-200/70 bg-[var(--color-warm-2)]">
      {/* brand */}
      <div className="flex h-14 items-center gap-2.5 px-4">
        <img
          src="/logo-sm.png"
          alt="Chameleon"
          className="h-7 w-7 flex-shrink-0 object-contain"
        />
        <span className="text-[15.5px] font-semibold tracking-tight text-stone-800">
          Chameleon
        </span>
        <button
          onClick={onToggle}
          className="ml-auto rounded-md p-1 text-stone-500 transition hover:bg-stone-200/60 hover:text-stone-800"
          title="折叠侧栏"
        >
          <PanelLeftClose className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* P19.3：workspace 切换器 */}
      <WorkspaceSwitcher />

      {/* nav */}
      <nav className="flex-1 space-y-0.5 overflow-auto px-3 pb-2 pt-1 text-[14px]">
        {hydrated &&
          visibleLeaves(TOP_ITEMS).map(item => (
            <NavLeafItem key={item.to} item={item} active={isActive(item.to)} />
          ))}

        {visibleAi && (
          <>
            <SectionLabel i18nKey={AI_GROUP.i18nKey} fallback={AI_GROUP.fallbackTitle} />
            <NavGroupItem
              group={visibleAi}
              activePath={pathname}
              open={openGroups[AI_GROUP.to]}
              onToggle={() => toggleGroup(AI_GROUP.to)}
            />
          </>
        )}

        {visibleAccess && (
          <>
            <SectionLabel i18nKey={ACCESS_GROUP.i18nKey} fallback={ACCESS_GROUP.fallbackTitle} />
            <NavGroupItem
              group={visibleAccess}
              activePath={pathname}
              open={openGroups[ACCESS_GROUP.to]}
              onToggle={() => toggleGroup(ACCESS_GROUP.to)}
            />
          </>
        )}

        {sysVisible.length > 0 && (
          <>
            <SectionLabel i18nKey="menu.group.system" fallback="系统" />
            {sysVisible.map(item => (
              <NavLeafItem key={item.to} item={item} active={isActive(item.to)} />
            ))}
          </>
        )}
      </nav>

      <BottomUser />
    </aside>
  );
};

// ── 分组标题（UPPERCASE 11px） ───────────────────────────
const SectionLabel = ({ i18nKey, fallback }: { i18nKey: string; fallback: string }) => {
  const { t } = useTranslation();
  return (
    <div className="px-3 pb-1 pt-3 text-[11px] font-medium uppercase tracking-wider text-stone-400">
      {t(i18nKey, fallback)}
    </div>
  );
};

// ── NavLeaf ───────────────────────────────────────────
const NavLeafItem = ({ item, active }: { item: NavLeaf; active: boolean }) => {
  const Icon = item.icon;
  const { t } = useTranslation();
  return (
    <Link
      to={item.to}
      className={cn(
        'flex items-center gap-3 rounded-lg px-3 py-1.5 transition',
        active
          ? 'bg-[var(--color-paper)] text-stone-900 shadow-[var(--shadow-soft)]'
          : 'text-stone-700 hover:bg-[var(--color-paper)] hover:shadow-[var(--shadow-soft)]',
      )}
    >
      <Icon
        className={cn(
          'h-[17px] w-[17px] flex-shrink-0',
          active ? 'text-blue-600' : 'text-stone-500',
        )}
      />
      <span className={active ? 'font-medium' : ''}>{t(item.i18nKey, item.fallbackTitle)}</span>
      {item.badge ? <span className="ml-auto">{item.badge}</span> : null}
    </Link>
  );
};

// ── NavGroup（可折叠 + 子项 tree-line） ─────────────────
const NavGroupItem = ({
  group,
  activePath,
  open,
  onToggle,
}: {
  group: NavGroup;
  activePath: string;
  open: boolean;
  onToggle: () => void;
}) => {
  const Icon = group.icon;
  const { t } = useTranslation();
  const isGroupActive =
    activePath === group.to || activePath.startsWith(group.to + '/');

  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        className={cn(
          'flex w-full items-center gap-3 rounded-lg px-3 py-1.5 text-left transition',
          isGroupActive
            ? 'bg-[var(--color-paper)] text-stone-900 shadow-[var(--shadow-soft)]'
            : 'text-stone-700 hover:bg-[var(--color-paper)] hover:shadow-[var(--shadow-soft)]',
        )}
      >
        <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center rounded text-stone-400">
          {open ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
        </span>
        <Icon
          className={cn(
            'h-[17px] w-[17px] flex-shrink-0',
            isGroupActive ? 'text-blue-600' : 'text-stone-500',
          )}
        />
        <span className={cn('flex-1 truncate', isGroupActive && 'font-medium')}>
          {t(group.i18nKey, group.fallbackTitle)}
        </span>
      </button>

      {open && group.children.length > 0 && (
        <div className="tree-line ml-4 mt-0.5 space-y-0.5">
          {group.children.map(child => {
            const childActive = activePath === child.to;
            const ChildIcon = child.icon;
            return (
              <Link
                key={child.to}
                to={child.to}
                className={cn(
                  'tree-item flex items-center gap-2 rounded-lg py-1.5 pl-8 pr-3 text-[13.5px] transition',
                  childActive
                    ? 'bg-blue-50/70 font-medium text-blue-700'
                    : 'text-stone-600 hover:bg-[var(--color-paper)]',
                )}
              >
                <ChildIcon
                  className={cn(
                    'h-4 w-4 flex-shrink-0',
                    childActive ? 'text-blue-600' : 'text-stone-400',
                  )}
                />
                <span className="flex-1 truncate">{t(child.i18nKey, child.fallbackTitle)}</span>
                {child.badge}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
};

// ── 底部用户菜单 ─────────────────────────────────────────
const BottomUser = () => {
  const user = useAuthStore(s => s.user);
  const logout = useAuthStore(s => s.logout);
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();

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
          title="账户菜单"
          className="group flex w-full items-center gap-2.5 border-t border-stone-200/70 bg-transparent p-2.5 text-left outline-none transition hover:bg-stone-200/40 focus-visible:bg-stone-200/40"
        >
          <img
            src="/default-avatar.jpg"
            alt={username}
            className="h-7 w-7 flex-shrink-0 rounded-full object-cover"
          />
          <div className="min-w-0 flex-1">
            <div className="truncate text-[12px] text-stone-800">{username}</div>
            <div className="flex items-center gap-1 text-[10px] text-stone-500">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              在线
            </div>
          </div>
          <Settings className="h-3.5 w-3.5 flex-shrink-0 text-stone-400 transition group-hover:text-stone-700" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" side="top" className="w-56">
        <DropdownMenuLabel className="font-normal">
          <div className="font-medium text-stone-900">{username}</div>
          {email && <div className="text-xs text-stone-500">{email}</div>}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        <DropdownMenuItem
          onClick={() => setLanguage('zh-CN')}
          className={i18n.language === 'zh-CN' ? 'bg-stone-100' : ''}
        >
          <Globe className="mr-2 h-3.5 w-3.5 text-stone-500" /> 简体中文
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => setLanguage('en-US')}
          className={i18n.language === 'en-US' ? 'bg-stone-100' : ''}
        >
          <Globe className="mr-2 h-3.5 w-3.5 text-stone-500" /> English
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => navigate('/change-password')}>
          <KeyRound className="mr-2 h-3.5 w-3.5 text-stone-500" />
          {t('topbar.change_password', '修改密码')}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleLogout} className="text-red-600">
          <LogOut className="mr-2 h-3.5 w-3.5" /> {t('topbar.logout', '退出登录')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

// ── 折叠态：48px icon-only ────────────────────────────────
const CollapsedSidebar = ({
  pathname,
  onToggle,
  visibleTop,
  visibleAi,
  visibleAccess,
  visibleSystem,
}: {
  pathname: string;
  onToggle: () => void;
  visibleTop: NavLeaf[];
  visibleAi: NavGroup | null;
  visibleAccess: NavGroup | null;
  visibleSystem: NavLeaf[];
}) => {
  const { t } = useTranslation();
  const allItems: NavLeaf[] = [
    ...visibleTop,
    ...(visibleAi ? visibleAi.children : []),
    ...(visibleAccess ? visibleAccess.children : []),
    ...visibleSystem,
  ];

  return (
    <aside className="flex h-full w-14 flex-shrink-0 flex-col items-center border-r border-stone-200/70 bg-[var(--color-warm-2)] py-2">
      <button
        type="button"
        onClick={onToggle}
        className="mb-1 flex h-10 w-10 items-center justify-center rounded-lg transition hover:bg-[var(--color-paper)] hover:shadow-[var(--shadow-soft)]"
        title="展开侧栏"
      >
        <img src="/logo-sm.png" alt="Chameleon" className="h-9 w-9 object-contain" />
      </button>
      <button
        type="button"
        onClick={onToggle}
        className="mb-1 flex h-7 w-9 items-center justify-center rounded-md text-stone-500 transition hover:bg-stone-200/60 hover:text-stone-800"
        title="展开侧栏"
      >
        <PanelLeftOpen className="h-[15px] w-[15px]" />
      </button>
      <nav className="flex-1 space-y-1 overflow-y-auto overflow-x-hidden">
        {allItems.map(item => {
          const active = pathname === item.to || pathname.startsWith(item.to + '/');
          const Icon = item.icon;
          return (
            <Link
              key={item.to}
              to={item.to}
              title={t(item.i18nKey, item.fallbackTitle)}
              className={cn(
                'group flex h-9 w-9 items-center justify-center rounded-lg transition',
                active
                  ? 'bg-[var(--color-paper)] text-blue-600 shadow-[var(--shadow-soft)]'
                  : 'text-stone-600 hover:bg-[var(--color-paper)] hover:shadow-[var(--shadow-soft)]',
              )}
            >
              <Icon className="h-[17px] w-[17px]" />
            </Link>
          );
        })}
      </nav>
    </aside>
  );
};

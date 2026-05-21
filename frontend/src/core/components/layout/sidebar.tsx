/** 主侧边栏（参考 waveflow 风格） */

import {
  Activity,
  Bot,
  ChevronLeft,
  ChevronRight,
  Cpu,
  Database,
  FileCog,
  Globe,
  KeySquare,
  LayoutDashboard,
  Newspaper,
  Settings,
  ShieldCheck,
  Sparkles,
  Users2,
} from 'lucide-react';
import type { ComponentType } from 'react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';

import { cn } from '@/core/lib/cn';
import { useAuthStore } from '@/core/stores/auth-store';

interface MenuItem {
  path: string;
  i18nKey: string;
  fallbackTitle: string;
  icon: ComponentType<{ className?: string }>;
  perm?: string;
}

interface MenuGroup {
  i18nLabel: string;
  fallbackLabel: string;
  items: MenuItem[];
}

const GROUPS: MenuGroup[] = [
  {
    i18nLabel: 'menu.group.overview',
    fallbackLabel: '总览',
    items: [
      { path: '/dashboard', i18nKey: 'menu.dashboard', fallbackTitle: '仪表盘', icon: LayoutDashboard, perm: 'dashboard:read' },
    ],
  },
  {
    i18nLabel: 'menu.group.ai',
    fallbackLabel: 'AI 能力',
    items: [
      { path: '/agents', i18nKey: 'menu.agents', fallbackTitle: '智能体', icon: Bot, perm: 'agents:read' },
      { path: '/providers', i18nKey: 'menu.providers', fallbackTitle: 'Providers', icon: Globe, perm: 'providers:read' },
      { path: '/models', i18nKey: 'menu.models', fallbackTitle: '模型', icon: Sparkles, perm: 'models:read' },
      { path: '/kbs', i18nKey: 'menu.kbs', fallbackTitle: '知识库', icon: Database, perm: 'kbs:read' },
      { path: '/embed-configs', i18nKey: 'menu.embed_configs', fallbackTitle: '嵌入式', icon: Cpu, perm: 'embed_configs:read' },
    ],
  },
  {
    i18nLabel: 'menu.group.access',
    fallbackLabel: '应用 & 调用',
    items: [
      { path: '/apps', i18nKey: 'menu.apps', fallbackTitle: '应用 & API Key', icon: KeySquare, perm: 'apps:read' },
      { path: '/call-logs', i18nKey: 'menu.call_logs', fallbackTitle: '调用日志', icon: Activity, perm: 'call_logs:read' },
      { path: '/users', i18nKey: 'menu.users', fallbackTitle: '用户', icon: Users2, perm: 'users:read' },
      { path: '/roles', i18nKey: 'menu.roles', fallbackTitle: '角色', icon: ShieldCheck, perm: 'roles:read' },
    ],
  },
  {
    i18nLabel: 'menu.group.system',
    fallbackLabel: '系统',
    items: [
      { path: '/audit-logs', i18nKey: 'menu.audit_logs', fallbackTitle: '审计日志', icon: Newspaper, perm: 'audit_logs:read' },
      { path: '/settings', i18nKey: 'menu.settings', fallbackTitle: '系统配置', icon: Settings, perm: 'settings:read' },
      { path: '/system-info', i18nKey: 'menu.about', fallbackTitle: '关于', icon: FileCog },
    ],
  },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export const Sidebar = ({ collapsed, onToggle }: SidebarProps) => {
  const location = useLocation();
  const { t } = useTranslation();
  const hasPermission = useAuthStore(s => s.hasPermission);
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => setHydrated(true), []);

  return (
    <aside
      className={cn(
        'flex flex-col border-r border-stone-200 bg-[var(--color-paper)] transition-all',
        collapsed ? 'w-16' : 'w-60',
      )}
    >
      {/* logo */}
      <div className="flex h-14 items-center gap-2 border-b border-stone-200 px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary-600 font-serif text-white shadow-soft">
          C
        </div>
        {!collapsed && (
          <span className="font-serif text-lg tracking-tight text-stone-900">Chameleon</span>
        )}
      </div>

      {/* menu */}
      <nav className="flex-1 overflow-y-auto py-3">
        {GROUPS.map(group => {
          const visible = group.items.filter(it => !it.perm || (hydrated && hasPermission(it.perm)));
          if (!hydrated) {
            // SSR / first paint：先全部显示，挂载后过滤
            // 这里 hydrated=false 时不渲染，避免 flash；首次挂载会立即转 true
            return null;
          }
          if (visible.length === 0) return null;
          const groupLabel = t(group.i18nLabel, group.fallbackLabel);
          return (
            <div key={group.i18nLabel} className="mb-4">
              {!collapsed && (
                <div className="px-4 mb-1 text-[10px] font-semibold uppercase tracking-wider text-stone-400">
                  {groupLabel}
                </div>
              )}
              {visible.map(item => {
                const active = location.pathname.startsWith(item.path);
                const Icon = item.icon;
                const itemLabel = t(item.i18nKey, item.fallbackTitle);
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={cn(
                      'mx-2 flex h-9 items-center gap-3 rounded-md px-3 text-sm transition-colors',
                      active
                        ? 'bg-primary-50 text-primary-700 font-medium'
                        : 'text-stone-700 hover:bg-stone-100',
                      collapsed && 'justify-center px-0',
                    )}
                    title={collapsed ? itemLabel : undefined}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {!collapsed && <span>{itemLabel}</span>}
                  </Link>
                );
              })}
            </div>
          );
        })}
      </nav>

      {/* collapse toggle */}
      <button
        type="button"
        onClick={onToggle}
        className="flex h-10 items-center justify-center border-t border-stone-200 text-stone-500 hover:bg-stone-50"
      >
        {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
      </button>
    </aside>
  );
};

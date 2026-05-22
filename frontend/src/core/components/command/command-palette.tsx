/** ⌘K 全站命令面板 —— 搜索 + 跳转 + 动作 + 最近访问 */

import { useQuery } from '@tanstack/react-query';
import { Command } from 'cmdk';
import {
  Bot,
  Cloud,
  Code2,
  Cpu,
  Download,
  FileText,
  History,
  Key,
  KeyRound,
  LayoutDashboard,
  Library,
  LogOut,
  Plus,
  Puzzle,
  Search,
  Settings,
  Shield,
  Users,
} from 'lucide-react';
import * as React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { cn } from '@/core/lib/cn';
import { searchApi, type SearchType } from '@/system/search/services/search';

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  bot: Bot,
  cpu: Cpu,
  cloud: Cloud,
  library: Library,
  key: Key,
  users: Users,
  puzzle: Puzzle,
};

const TYPE_LABEL: Record<SearchType, string> = {
  agent: 'Agent',
  model: 'Model',
  provider: 'Provider',
  kb: '知识库',
  app: '应用',
  user: '用户',
  embed_config: '嵌入配置',
};

interface NavItem {
  label: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
  keywords?: string;
}

const NAV_ITEMS: NavItem[] = [
  { label: '仪表盘', path: '/dashboard', icon: LayoutDashboard, keywords: 'dashboard' },
  { label: '用户管理', path: '/users', icon: Users, keywords: 'user 用户' },
  { label: '角色管理', path: '/roles', icon: Shield, keywords: 'role 角色' },
  { label: '应用 API Key', path: '/apps', icon: Key, keywords: 'app 应用' },
  { label: 'Providers', path: '/providers', icon: Cloud, keywords: 'provider 厂商' },
  { label: 'Models', path: '/models', icon: Cpu, keywords: 'model 模型' },
  { label: 'Agents', path: '/agents', icon: Bot, keywords: 'agent' },
  { label: '知识库', path: '/kbs', icon: Library, keywords: 'kb knowledge' },
  { label: '嵌入配置', path: '/embed-configs', icon: Puzzle, keywords: 'embed widget' },
  { label: '调用日志', path: '/call-logs', icon: FileText, keywords: 'call log' },
  { label: '审计日志', path: '/audit-logs', icon: History, keywords: 'audit log' },
  { label: '系统设置', path: '/settings', icon: Settings, keywords: 'settings 设置' },
];

interface RecentEntry {
  path: string;
  label: string;
  at: number;
}

const RECENT_KEY = 'chameleon.recent_pages';
const RECENT_MAX = 8;

function getRecent(): RecentEntry[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw) as RecentEntry[];
    return Array.isArray(arr) ? arr.slice(0, RECENT_MAX) : [];
  } catch {
    return [];
  }
}

export function pushRecent(path: string, label: string) {
  try {
    const list = getRecent().filter(e => e.path !== path);
    list.unshift({ path, label, at: Date.now() });
    localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, RECENT_MAX)));
  } catch {
    /* ignore */
  }
}

interface Action {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  onSelect: (nav: ReturnType<typeof useNavigate>) => void;
  keywords?: string;
}

const ACTIONS: Action[] = [
  {
    label: '创建 Agent',
    icon: Plus,
    onSelect: nav => nav('/agents?create=1'),
    keywords: 'create agent 新建',
  },
  {
    label: '创建知识库',
    icon: Plus,
    onSelect: nav => nav('/kbs?create=1'),
    keywords: 'create kb knowledge',
  },
  {
    label: '创建应用',
    icon: Plus,
    onSelect: nav => nav('/apps?create=1'),
    keywords: 'create app',
  },
  {
    label: '导出全部配置',
    icon: Download,
    onSelect: nav => nav('/settings'),
    keywords: 'export 备份',
  },
  {
    label: '修改密码',
    icon: KeyRound,
    onSelect: nav => nav('/change-password'),
    keywords: 'password',
  },
  {
    label: '退出登录',
    icon: LogOut,
    onSelect: () => {
      localStorage.removeItem('chameleon.access_token');
      localStorage.removeItem('chameleon.refresh_token');
      location.href = '/login';
    },
    keywords: 'logout 退出',
  },
];

export const CommandPalette: React.FC = () => {
  useTranslation();
  const [open, setOpen] = React.useState(false);
  const [q, setQ] = React.useState('');
  const navigate = useNavigate();

  // 全局 ⌘K / Ctrl+K
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen(o => !o);
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, []);

  // 防抖搜索：q 改变后 200ms 才请求
  const [debouncedQ, setDebouncedQ] = React.useState('');
  React.useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q.trim()), 200);
    return () => clearTimeout(t);
  }, [q]);

  const searchQ = useQuery({
    queryKey: ['cmdk-search', debouncedQ],
    queryFn: () => searchApi.search(debouncedQ),
    enabled: open && debouncedQ.length > 0,
    staleTime: 30 * 1000,
  });

  const go = (path: string, label?: string) => {
    if (label) pushRecent(path, label);
    setOpen(false);
    setQ('');
    navigate(path);
  };

  const recent = React.useMemo(() => (open ? getRecent() : []), [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center bg-stone-950/40 backdrop-blur-sm">
      <div
        role="button"
        aria-label="关闭"
        tabIndex={-1}
        className="absolute inset-0"
        onClick={() => setOpen(false)}
      />
      <Command
        loop
        label="命令面板"
        className={cn(
          'relative mt-[10vh] w-[600px] max-w-[90vw] overflow-hidden rounded-xl border border-stone-200 bg-paper shadow-pop',
          'flex flex-col max-h-[70vh]',
        )}
        shouldFilter={true}
      >
        <div className="flex items-center gap-2 border-b border-stone-100 px-4">
          <Search className="h-4 w-4 text-stone-400" strokeWidth={1.75} />
          <Command.Input
            autoFocus
            value={q}
            onValueChange={setQ}
            placeholder="搜索 agent / model / KB / app / user，或输入命令"
            className="flex h-12 w-full bg-transparent text-[13.5px] text-stone-800 placeholder:text-stone-400 outline-none"
          />
          <kbd className="hidden rounded border border-stone-200 px-1.5 py-0.5 text-[10px] font-mono text-stone-400 sm:inline-block">
            Esc
          </kbd>
        </div>
        <Command.List className="flex-1 overflow-y-auto px-2 py-2">
          <Command.Empty className="py-8 text-center text-[12.5px] text-stone-400">
            没有匹配项。试试搜索 agent 名 / model 名 / app_key。
          </Command.Empty>

          {/* 搜索结果（仅有 query 时显示） */}
          {debouncedQ && (searchQ.data?.results.length ?? 0) > 0 ? (
            <Command.Group heading="搜索结果" className="cmdk-group">
              {(searchQ.data?.results ?? []).map(r => {
                const Icon = ICON_MAP[r.icon] || Search;
                return (
                  <Command.Item
                    key={`${r.type}-${r.id}`}
                    value={`${r.type} ${r.title} ${r.snippet}`}
                    onSelect={() => go(r.url, r.title)}
                    className="cmdk-item"
                  >
                    <Icon className="h-3.5 w-3.5 text-stone-400" />
                    <span className="flex-1 truncate">
                      <span className="font-medium text-stone-800">{r.title}</span>
                      <span className="ml-2 font-mono text-[10.5px] text-stone-400">{r.snippet}</span>
                    </span>
                    <span className="rounded bg-stone-100 px-1.5 py-0.5 text-[10px] font-medium text-stone-500">
                      {TYPE_LABEL[r.type]}
                    </span>
                  </Command.Item>
                );
              })}
            </Command.Group>
          ) : null}

          {/* 跳转 */}
          <Command.Group heading="跳转" className="cmdk-group">
            {NAV_ITEMS.map(item => {
              const Icon = item.icon;
              return (
                <Command.Item
                  key={item.path}
                  value={`${item.label} ${item.keywords || ''}`}
                  onSelect={() => go(item.path, item.label)}
                  className="cmdk-item"
                >
                  <Icon className="h-3.5 w-3.5 text-stone-400" />
                  <span className="flex-1 text-stone-700">{item.label}</span>
                  <span className="font-mono text-[10.5px] text-stone-400">{item.path}</span>
                </Command.Item>
              );
            })}
          </Command.Group>

          {/* 动作 */}
          <Command.Group heading="动作" className="cmdk-group">
            {ACTIONS.map(a => {
              const Icon = a.icon;
              return (
                <Command.Item
                  key={a.label}
                  value={`${a.label} ${a.keywords || ''}`}
                  onSelect={() => {
                    a.onSelect(navigate);
                    setOpen(false);
                    setQ('');
                  }}
                  className="cmdk-item"
                >
                  <Icon className="h-3.5 w-3.5 text-stone-400" />
                  <span className="flex-1 text-stone-700">{a.label}</span>
                </Command.Item>
              );
            })}
          </Command.Group>

          {/* 最近访问（仅无 query 时） */}
          {!debouncedQ && recent.length > 0 ? (
            <Command.Group heading="最近访问" className="cmdk-group">
              {recent.map(e => (
                <Command.Item
                  key={e.path}
                  value={`recent ${e.label} ${e.path}`}
                  onSelect={() => go(e.path)}
                  className="cmdk-item"
                >
                  <History className="h-3.5 w-3.5 text-stone-400" />
                  <span className="flex-1 text-stone-700">{e.label}</span>
                  <span className="font-mono text-[10.5px] text-stone-400">{e.path}</span>
                </Command.Item>
              ))}
            </Command.Group>
          ) : null}
        </Command.List>
        <div className="flex items-center gap-3 border-t border-stone-100 bg-warm-2/30 px-3 py-2 text-[10.5px] text-stone-400">
          <span>
            <kbd className="rounded border border-stone-200 bg-paper px-1 py-0.5 font-mono">↑↓</kbd> 导航
          </span>
          <span>
            <kbd className="rounded border border-stone-200 bg-paper px-1 py-0.5 font-mono">⏎</kbd> 选择
          </span>
          <span className="ml-auto flex items-center gap-1">
            <Code2 className="h-3 w-3" />
            <kbd className="rounded border border-stone-200 bg-paper px-1 py-0.5 font-mono">⌘K</kbd>
          </span>
        </div>
      </Command>
    </div>
  );
};

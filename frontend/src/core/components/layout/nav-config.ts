/** 导航 IA —— 两级结构：顶部域(Domain) × 域内二级导航(Group→Leaf)
 *
 * 顶栏切「域」（工作台 / 知识库 / 观测 / 设置），
 * 左侧无边导航展示当前域的分组与叶子项。
 *
 * 单一数据源：top-bar 与 secondary-nav 都从这里取，避免两处维护漂移。
 */
import type { ComponentType } from 'react';

import {
  Activity,
  Boxes,
  Database,
  DollarSign,
  FlaskConical,
  Globe,
  KeySquare,
  LayoutDashboard,
  MessageSquare,
  Newspaper,
  Puzzle,
  ScrollText,
  Settings,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  Telescope,
  Users2,
} from 'lucide-react';

type Icon = ComponentType<{ className?: string }>;

export interface NavLeaf {
  to: string;
  icon: Icon;
  i18nKey: string;
  fallbackTitle: string;
  perm?: string;
}

export interface NavGroup {
  i18nKey: string;
  fallbackTitle: string;
  children: NavLeaf[];
}

export interface NavDomain {
  key: string;
  /** 点击域 tab 的落地路由（取首个可见叶子即可，这里显式指定更可控） */
  to: string;
  icon: Icon;
  i18nKey: string;
  fallbackTitle: string;
  groups: NavGroup[];
}

export const DOMAINS: NavDomain[] = [
  // ── 工作台：造能力（应用/工作流/对话/嵌入）+ 接入（模型/插件）──
  {
    key: 'work',
    to: '/agents',
    icon: Boxes,
    i18nKey: 'menu.domain.work',
    fallbackTitle: '工作台',
    groups: [
      {
        i18nKey: 'menu.group.create',
        fallbackTitle: '创建',
        children: [
          { to: '/agents', icon: Boxes, i18nKey: 'menu.agents', fallbackTitle: '应用', perm: 'agents:read' },
        ],
      },
    ],
  },

  // ── 知识库 ──
  {
    key: 'kb',
    to: '/kbs',
    icon: Database,
    i18nKey: 'menu.domain.kb',
    fallbackTitle: '知识库',
    groups: [
      {
        i18nKey: 'menu.group.knowledge',
        fallbackTitle: '知识',
        children: [{ to: '/kbs', icon: Database, i18nKey: 'menu.kbs', fallbackTitle: '知识库', perm: 'kbs:read' }],
      },
    ],
  },

  // ── 观测与评估 ──
  {
    key: 'observe',
    to: '/dashboard',
    icon: Telescope,
    i18nKey: 'menu.domain.observe',
    fallbackTitle: '观测',
    groups: [
      {
        i18nKey: 'menu.group.overview',
        fallbackTitle: '概览',
        children: [
          { to: '/dashboard', icon: LayoutDashboard, i18nKey: 'menu.dashboard', fallbackTitle: '仪表盘', perm: 'dashboard:read' },
        ],
      },
      {
        i18nKey: 'menu.group.runs',
        fallbackTitle: '运行记录',
        children: [
          { to: '/sessions', icon: ScrollText, i18nKey: 'menu.sessions', fallbackTitle: '会话 & 运行', perm: 'call_logs:read' },
          { to: '/traces', icon: Activity, i18nKey: 'menu.trace', fallbackTitle: 'Trace', perm: 'call_logs:read' },
          {
            to: '/playground',
            icon: MessageSquare,
            i18nKey: 'menu.playground',
            fallbackTitle: '对话 / Playground',
            perm: 'playground:invoke',
          },
        ],
      },
      {
        i18nKey: 'menu.group.quality',
        fallbackTitle: '质量 & 成本',
        children: [
          { to: '/dashboard/cost', icon: DollarSign, i18nKey: 'menu.cost', fallbackTitle: '成本统计', perm: 'call_logs:read' },
          { to: '/datasets', icon: Database, i18nKey: 'menu.datasets', fallbackTitle: 'Datasets', perm: 'datasets:read' },
          { to: '/eval-jobs', icon: FlaskConical, i18nKey: 'menu.eval_jobs', fallbackTitle: '评测任务', perm: 'datasets:read' },
        ],
      },
      {
        i18nKey: 'menu.group.compliance',
        fallbackTitle: '合规',
        children: [
          { to: '/audit-logs', icon: Newspaper, i18nKey: 'menu.audit_logs', fallbackTitle: '审计日志', perm: 'audit_logs:read' },
        ],
      },
    ],
  },

  // ── 设置 ──
  {
    key: 'settings',
    to: '/providers',
    icon: Settings,
    i18nKey: 'menu.domain.settings',
    fallbackTitle: '设置',
    groups: [
      {
        i18nKey: 'menu.group.access_in',
        fallbackTitle: '接入',
        children: [
          { to: '/providers', icon: Globe, i18nKey: 'menu.providers', fallbackTitle: 'Providers', perm: 'providers:read' },
          { to: '/models', icon: Sparkles, i18nKey: 'menu.models', fallbackTitle: '模型', perm: 'models:read' },
          { to: '/plugins', icon: Puzzle, i18nKey: 'menu.plugins', fallbackTitle: '插件', perm: 'plugins:read' },
          { to: '/marketplace', icon: ShoppingBag, i18nKey: 'menu.marketplace', fallbackTitle: '插件市场', perm: 'plugins:read' },
        ],
      },
      {
        i18nKey: 'menu.group.access',
        fallbackTitle: '访问',
        children: [
          { to: '/api-keys', icon: KeySquare, i18nKey: 'menu.api_keys', fallbackTitle: 'Key 管理', perm: 'api_keys:read' },
          { to: '/users', icon: Users2, i18nKey: 'menu.users', fallbackTitle: '用户管理', perm: 'users:read' },
          { to: '/roles', icon: ShieldCheck, i18nKey: 'menu.roles', fallbackTitle: '角色管理', perm: 'roles:read' },
        ],
      },
      {
        i18nKey: 'menu.group.platform',
        fallbackTitle: '平台',
        children: [
          { to: '/settings', icon: Settings, i18nKey: 'menu.settings', fallbackTitle: '系统配置', perm: 'settings:read' },
        ],
      },
    ],
  },
];

/** 路由是否命中某叶子（精确 or 子路径） */
function matchLen(pathname: string, to: string): number {
  if (pathname === to) return to.length + 1; // 精确优先
  if (pathname.startsWith(to + '/')) return to.length;
  return 0;
}

/** 由当前路由推断所属域：取「最长命中叶子」所在域，命中不到则回退首个域 */
export function findActiveDomain(pathname: string): NavDomain {
  let best: { domain: NavDomain; len: number } | null = null;
  for (const d of DOMAINS) {
    for (const g of d.groups) {
      for (const l of g.children) {
        const len = matchLen(pathname, l.to);
        if (len > 0 && (!best || len > best.len)) best = { domain: d, len };
      }
    }
  }
  return best?.domain ?? DOMAINS[0];
}

/** 在给定叶子集合中，返回当前路由命中的「唯一」叶子 to（最长命中），无则空串 */
export function activeLeafTo(pathname: string, leaves: NavLeaf[]): string {
  let bestTo = '';
  let bestLen = 0;
  for (const l of leaves) {
    const len = matchLen(pathname, l.to);
    if (len > bestLen) {
      bestLen = len;
      bestTo = l.to;
    }
  }
  return bestTo;
}

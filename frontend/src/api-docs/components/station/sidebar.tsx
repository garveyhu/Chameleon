/** 左侧导航 —— 分组折叠 + 端点列表 + 顶部搜索
 *
 * 单一职责：把 grouped endpoints 渲染成可折叠树，点项调 onSelect。
 * 搜索只对当前列表客户端过滤（title/path/desc 文本匹配）。
 */
import * as React from 'react';

import { ChevronDown, ChevronRight, Search } from 'lucide-react';

import type { GroupedEndpoints } from '@/api-docs/registry/_collect';
import type { EndpointSpec } from '@/api-docs/types/endpoint';
import { cn } from '@/core/lib/cn';

import { MethodPill } from './method-pill';

interface Props {
  groups: GroupedEndpoints[];
  activeId: string;
  onSelect: (id: string) => void;
  /** 与外部搜索框共享的关键字，外部按 ⌘K focus 用 */
  searchInputRef?: React.RefObject<HTMLInputElement | null>;
}

export const Sidebar = ({ groups, activeId, onSelect, searchInputRef }: Props) => {
  const [keyword, setKeyword] = React.useState('');
  const [collapsed, setCollapsed] = React.useState<Record<string, boolean>>({});

  const kw = keyword.trim().toLowerCase();
  const matches = (e: EndpointSpec) => {
    if (!kw) return true;
    if (e.title.toLowerCase().includes(kw)) return true;
    if (e.path.toLowerCase().includes(kw)) return true;
    if (typeof e.desc === 'string' && e.desc.toLowerCase().includes(kw)) return true;
    return false;
  };

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-stone-200/70 bg-[var(--color-paper)]">
      {/* 搜索 */}
      <div className="border-b border-stone-200/70 px-4 py-3">
        <div className="flex items-center gap-2 rounded-lg border border-stone-200 bg-stone-50 px-2.5 py-1.5 focus-within:border-blue-300 focus-within:ring-2 focus-within:ring-blue-100">
          <Search className="h-3.5 w-3.5 text-stone-400" />
          <input
            ref={searchInputRef}
            type="text"
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
            placeholder="搜索接口（⌘K）"
            className="min-w-0 flex-1 bg-transparent text-[12.5px] text-stone-700 outline-none placeholder:text-stone-400"
          />
          {!keyword && (
            <kbd className="hidden shrink-0 rounded border border-stone-200 bg-white px-1 font-mono text-[10px] text-stone-400 sm:inline">
              ⌘K
            </kbd>
          )}
        </div>
      </div>

      {/* 分组列表 */}
      <nav className="flex-1 overflow-y-auto px-2 py-3">
        {groups.map(({ group, endpoints }) => {
          const visibleEps = endpoints.filter(matches);
          // 搜索状态下空分组隐藏；非搜索状态保留可折叠
          if (kw && visibleEps.length === 0) return null;
          const folded = collapsed[group.key] === true;
          return (
            <div key={group.key} className="mb-2">
              <button
                type="button"
                onClick={() => setCollapsed(s => ({ ...s, [group.key]: !folded }))}
                className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-[11px] font-semibold tracking-[0.04em] text-stone-500 uppercase hover:bg-stone-100/70"
              >
                {folded ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                <span className="flex-1 truncate">{group.title}</span>
                <span className="rounded bg-stone-100 px-1.5 text-[10px] font-normal text-stone-400">
                  {visibleEps.length}
                </span>
              </button>
              {!folded && (
                <ul className="mt-0.5 ml-1.5 border-l border-stone-200/70 pl-1.5">
                  {visibleEps.map(e => {
                    const active = e.id === activeId;
                    return (
                      <li key={e.id}>
                        <button
                          type="button"
                          onClick={() => onSelect(e.id)}
                          className={cn(
                            'group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12.5px] transition',
                            active
                              ? 'bg-blue-50 font-medium text-blue-700'
                              : 'text-stone-700 hover:bg-stone-100/70',
                          )}
                        >
                          <MethodPill method={e.method} size="sm" />
                          <span className="min-w-0 flex-1 truncate">{e.title}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          );
        })}
      </nav>
    </aside>
  );
};

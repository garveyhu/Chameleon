/** AgentPicker —— 智能体筛选下拉（分页 + 搜索 + 向下滚动加载 + 左侧类别栏）
 *
 * 公共组件：随智能体增多，下拉走分页接口 /v1/admin/agents/options（搜索 + 类别筛）。
 * 左侧「应用类别」栏（代码 / 对话编排 / 流程编排 / 外部）只缩当前下拉列表，
 * 选中具体智能体 → onChange(agent_key)；选「全部应用」→ onChange('')。
 */

import { useInfiniteQuery } from '@tanstack/react-query';
import { Bot, Check, ChevronDown, Loader2, Search } from 'lucide-react';
import { useRef, useState } from 'react';

import { Input } from '@/core/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/core/components/ui/popover';
import { cn } from '@/core/lib/cn';
import { agentApi } from '@/system/agents/services/agent';
import type { AgentOption } from '@/system/agents/types/agent';

const CATEGORIES: { value: string; label: string }[] = [
  { value: '', label: '全部应用' },
  { value: 'local', label: '代码' },
  { value: 'graph-chatflow', label: '对话编排' },
  { value: 'graph-workflow', label: '流程编排' },
  { value: 'external', label: '外部' },
];

interface AgentPickerProps {
  /** 选中的 agent_key；'' = 全部 */
  value: string;
  onChange: (agentKey: string) => void;
  /** 触发器宽度（px），默认 168 */
  width?: number;
  className?: string;
}

export const AgentPicker = ({ value, onChange, width = 168, className }: AgentPickerProps) => {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState('');
  const [search, setSearch] = useState('');
  // 选中项的展示名（点选时记下；外部仅给 agent_key 时回退显示 key）
  const [picked, setPicked] = useState<AgentOption | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const q = useInfiniteQuery({
    queryKey: ['agent-options', search, category],
    queryFn: ({ pageParam }) =>
      agentApi.options({
        q: search || undefined,
        category: category || undefined,
        page: pageParam,
        page_size: 20,
      }),
    initialPageParam: 1,
    getNextPageParam: (last, pages) => {
      const loaded = pages.reduce((s, p) => s + p.items.length, 0);
      return loaded < last.total ? pages.length + 1 : undefined;
    },
    enabled: open,
  });
  const items = q.data?.pages.flatMap(p => p.items) ?? [];

  const onScroll = () => {
    const el = listRef.current;
    if (!el) return;
    if (
      el.scrollTop + el.clientHeight >= el.scrollHeight - 48 &&
      q.hasNextPage &&
      !q.isFetchingNextPage
    ) {
      void q.fetchNextPage();
    }
  };

  const triggerLabel =
    value === ''
      ? '全部应用'
      : picked && picked.agent_key === value
        ? picked.name
        : value;

  const select = (opt: AgentOption | null) => {
    setPicked(opt);
    onChange(opt ? opt.agent_key : '');
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          style={{ width }}
          className={cn(
            'flex h-7 items-center justify-between gap-1 rounded-md border border-stone-200 bg-white px-2 text-[12px] text-stone-700 transition hover:border-stone-300',
            className,
          )}
        >
          <span className="truncate">{triggerLabel}</span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-stone-400" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="!w-[420px] !p-0">
        <div className="flex h-[340px]">
          {/* 左：应用类别栏 */}
          <div className="w-24 shrink-0 space-y-0.5 overflow-y-auto border-r border-stone-100 p-1.5">
            {CATEGORIES.map(c => (
              <button
                key={c.value || 'all'}
                type="button"
                onClick={() => setCategory(c.value)}
                className={cn(
                  'w-full rounded px-2 py-1.5 text-left text-[12px] transition',
                  category === c.value
                    ? 'bg-blue-50 font-medium text-blue-700'
                    : 'text-stone-600 hover:bg-stone-100',
                )}
              >
                {c.label}
              </button>
            ))}
          </div>

          {/* 右：搜索 + 列表 */}
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="relative shrink-0 p-1.5">
              <Search className="pointer-events-none absolute top-1/2 left-3.5 h-3.5 w-3.5 -translate-y-1/2 text-stone-400" />
              <Input
                className="!h-7 pl-7 text-[12px]"
                placeholder="搜索名称 / key"
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>
            <div ref={listRef} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto p-1.5 pt-0">
              {/* 全部应用 */}
              <Row
                active={value === ''}
                onClick={() => select(null)}
                icon={<Bot className="h-3.5 w-3.5 text-stone-400" />}
                title="全部应用"
              />
              {items.map(opt => (
                <Row
                  key={opt.agent_key}
                  active={value === opt.agent_key}
                  onClick={() => select(opt)}
                  icon={
                    opt.icon ? (
                      <img src={opt.icon} alt="" className="h-4 w-4 rounded object-cover" />
                    ) : (
                      <Bot className="h-3.5 w-3.5 text-stone-400" />
                    )
                  }
                  title={opt.name}
                  sub={opt.agent_key}
                />
              ))}
              {q.isFetching ? (
                <div className="flex items-center justify-center gap-1.5 py-2 text-[11px] text-stone-400">
                  <Loader2 className="h-3 w-3 animate-spin" /> 加载中…
                </div>
              ) : items.length === 0 ? (
                <div className="py-6 text-center text-[12px] text-stone-400">无匹配应用</div>
              ) : !q.hasNextPage ? (
                <div className="py-2 text-center text-[10.5px] text-stone-300">没有更多了</div>
              ) : null}
            </div>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
};

const Row = ({
  active,
  onClick,
  icon,
  title,
  sub,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  title: string;
  sub?: string;
}) => (
  <button
    type="button"
    onClick={onClick}
    className={cn(
      'flex w-full items-center gap-2 rounded px-2 py-1.5 text-left transition hover:bg-stone-100',
      active && 'bg-blue-50',
    )}
  >
    <span className="shrink-0">{icon}</span>
    <span className="min-w-0 flex-1">
      <span className="block truncate text-[12px] text-stone-800">{title}</span>
      {sub ? <span className="block truncate font-mono text-[10px] text-stone-400">{sub}</span> : null}
    </span>
    {active ? <Check className="h-3.5 w-3.5 shrink-0 text-blue-600" /> : null}
  </button>
);

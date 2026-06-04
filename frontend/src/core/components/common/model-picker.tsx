/** ModelPicker —— chat 模型筛选下拉（搜索 + 左侧 provider 类别栏）
 *
 * 公共组件：照抄 agent-picker 的交互模式（Popover + 搜索 + 左侧类别栏 + onChange）。
 * 数据源 GET /v1/admin/models?kind=chat（modelApi.list）一次性返列表，前端按 provider
 * 分组 + 搜索过滤。选中具体模型 → onChange(model_code)；可选「不指定」→ onChange('')。
 */

import { useQuery } from '@tanstack/react-query';
import { Check, ChevronDown, Cpu, Loader2, Search } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Input } from '@/core/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/core/components/ui/popover';
import { cn } from '@/core/lib/cn';
import { modelApi } from '@/system/models/services/model';
import type { ModelItem } from '@/system/models/types/model';

interface ModelPickerProps {
  /** 选中的 model_code；'' = 不指定 */
  value: string;
  onChange: (modelCode: string) => void;
  /** 触发器占位文案 */
  placeholder?: string;
  /** 是否允许「不指定」选项（默认 true） */
  allowEmpty?: boolean;
  /** 触发器宽度（px），默认 168 */
  width?: number;
  className?: string;
}

const ALL_PROVIDERS = '__all__';

export const ModelPicker = ({
  value,
  onChange,
  placeholder = '选择模型',
  allowEmpty = true,
  width = 168,
  className,
}: ModelPickerProps) => {
  const [open, setOpen] = useState(false);
  const [provider, setProvider] = useState(ALL_PROVIDERS);
  const [search, setSearch] = useState('');

  const q = useQuery({
    queryKey: ['model-picker', 'chat'],
    queryFn: () => modelApi.list({ kind: 'chat' }),
    enabled: open,
    staleTime: 30_000,
  });

  const models = useMemo(
    () => (q.data ?? []).filter(m => m.enabled),
    [q.data],
  );

  // provider 类别栏：从数据派生（按 provider_code 去重）
  const providers = useMemo(() => {
    const seen = new Map<string, string>();
    for (const m of models) {
      const code = m.provider_code ?? '';
      if (code && !seen.has(code)) seen.set(code, code);
    }
    return [...seen.keys()];
  }, [models]);

  const filtered = useMemo(() => {
    const kw = search.trim().toLowerCase();
    return models.filter(m => {
      if (provider !== ALL_PROVIDERS && (m.provider_code ?? '') !== provider)
        return false;
      if (!kw) return true;
      return (
        m.code.toLowerCase().includes(kw) ||
        (m.provider_code ?? '').toLowerCase().includes(kw)
      );
    });
  }, [models, provider, search]);

  const triggerLabel = value === '' ? placeholder : value;

  const select = (m: ModelItem | null) => {
    onChange(m ? m.code : '');
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
            value === '' && 'text-stone-400',
            className,
          )}
        >
          <span className="truncate">{triggerLabel}</span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-stone-400" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="!w-[420px] !p-0">
        <div className="flex h-[340px]">
          {/* 左：provider 类别栏 */}
          <div className="w-24 shrink-0 space-y-0.5 overflow-y-auto border-r border-stone-100 p-1.5">
            <button
              type="button"
              onClick={() => setProvider(ALL_PROVIDERS)}
              className={cn(
                'w-full rounded px-2 py-1.5 text-left text-[12px] transition',
                provider === ALL_PROVIDERS
                  ? 'bg-blue-50 font-medium text-blue-700'
                  : 'text-stone-600 hover:bg-stone-100',
              )}
            >
              全部
            </button>
            {providers.map(p => (
              <button
                key={p}
                type="button"
                onClick={() => setProvider(p)}
                className={cn(
                  'w-full truncate rounded px-2 py-1.5 text-left text-[12px] transition',
                  provider === p
                    ? 'bg-blue-50 font-medium text-blue-700'
                    : 'text-stone-600 hover:bg-stone-100',
                )}
              >
                {p}
              </button>
            ))}
          </div>

          {/* 右：搜索 + 列表 */}
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="relative shrink-0 p-1.5">
              <Search className="pointer-events-none absolute top-1/2 left-3.5 h-3.5 w-3.5 -translate-y-1/2 text-stone-400" />
              <Input
                className="!h-7 pl-7 text-[12px]"
                placeholder="搜索模型名 / provider"
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-1.5 pt-0">
              {allowEmpty ? (
                <Row
                  active={value === ''}
                  onClick={() => select(null)}
                  title="不指定（用默认模型）"
                />
              ) : null}
              {filtered.map(m => (
                <Row
                  key={m.id}
                  active={value === m.code}
                  onClick={() => select(m)}
                  title={m.code}
                  sub={m.provider_code ?? undefined}
                />
              ))}
              {q.isFetching ? (
                <div className="flex items-center justify-center gap-1.5 py-2 text-[11px] text-stone-400">
                  <Loader2 className="h-3 w-3 animate-spin" /> 加载中…
                </div>
              ) : filtered.length === 0 ? (
                <div className="py-6 text-center text-[12px] text-stone-400">
                  无匹配模型
                </div>
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
  title,
  sub,
}: {
  active: boolean;
  onClick: () => void;
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
    <span className="shrink-0">
      <Cpu className="h-3.5 w-3.5 text-stone-400" />
    </span>
    <span className="min-w-0 flex-1">
      <span className="block truncate text-[12px] text-stone-800">{title}</span>
      {sub ? (
        <span className="block truncate font-mono text-[10px] text-stone-400">
          {sub}
        </span>
      ) : null}
    </span>
    {active ? <Check className="h-3.5 w-3.5 shrink-0 text-blue-600" /> : null}
  </button>
);

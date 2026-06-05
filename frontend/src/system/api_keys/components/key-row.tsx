/** KeyRow —— 单个 API Key 的密集列表行。
 *
 * 列表只展示 名称/作用域 + 描述(超出省略) + 最近使用 + 撤销 icon；
 * 不展示密钥明文/限额/状态（已撤销的不进列表）。点击整行打开详情弹窗看/复制密钥。
 */

import { Ban } from 'lucide-react';

import { cn } from '@/core/lib/cn';
import { formatRelative } from '@/core/lib/format';
import { scopeMeta } from '@/system/api_keys/scope';
import type { ApiKeyItem } from '@/system/api_keys/types/app';

interface Props {
  apiKey: ApiKeyItem;
  onOpen: () => void;
  onRevoke: () => void;
}

export const KeyRow = ({ apiKey: k, onOpen, onRevoke }: Props) => {
  const meta = scopeMeta(k.scope_type);
  const Icon = meta.icon;

  return (
    <div
      onClick={onOpen}
      className={cn(
        'group flex cursor-pointer items-center gap-3 border-l-[3px] px-3 py-2.5 transition hover:bg-stone-50',
        meta.accent,
      )}
    >
      <div className="flex w-48 shrink-0 items-center gap-2.5">
        <div className={cn('flex h-7 w-7 shrink-0 items-center justify-center rounded-md', meta.chip)}>
          <Icon className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-[12.5px] font-medium text-stone-900">{k.name}</div>
          <div className="truncate text-[10.5px] text-stone-400">
            {meta.label}
            {k.scope_ref ? ` · ${k.scope_ref}` : ''}
          </div>
        </div>
      </div>

      <div className="min-w-0 flex-1 truncate text-[11.5px] text-stone-500">
        {k.description || <span className="text-stone-300">—</span>}
      </div>

      <div className="hidden w-24 shrink-0 text-right text-[11px] text-stone-400 sm:block">
        {k.last_used_at ? formatRelative(k.last_used_at) : '从未使用'}
      </div>

      <button
        type="button"
        title="撤销"
        onClick={e => {
          e.stopPropagation();
          onRevoke();
        }}
        className="shrink-0 rounded-md p-1 text-stone-300 transition hover:bg-red-50 hover:text-red-600 group-hover:text-stone-400"
      >
        <Ban className="h-3.5 w-3.5" />
      </button>
    </div>
  );
};

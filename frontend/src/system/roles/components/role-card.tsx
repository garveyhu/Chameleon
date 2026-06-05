/** RoleCard —— 单个角色的现代卡片（替代表格行）。 */

import { Shield, ShieldCheck, Trash2 } from 'lucide-react';

import { Badge } from '@/core/components/ui/badge';
import { cn } from '@/core/lib/cn';
import type { RoleItem } from '@/system/roles/types/role';

interface Props {
  role: RoleItem;
  onPerms: () => void;
  onDelete: () => void;
}

export const RoleCard = ({ role: r, onPerms, onDelete }: Props) => (
  <div
    className={cn(
      'group flex flex-col rounded-xl border bg-[var(--color-paper)] p-4 transition hover:-translate-y-0.5 hover:shadow-pop',
      r.is_system ? 'border-sky-200' : 'border-stone-200 hover:border-stone-300',
    )}
  >
    <div className="flex items-start gap-3">
      <div
        className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
          r.is_system ? 'bg-sky-50 text-sky-600' : 'bg-stone-100 text-stone-500',
        )}
      >
        {r.is_system ? <ShieldCheck className="h-5 w-5" /> : <Shield className="h-5 w-5" />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[14px] font-medium text-stone-900">{r.name}</div>
        <div className="truncate font-mono text-[11px] text-stone-400">{r.code}</div>
      </div>
      {r.is_system ? (
        <Badge variant="primary">内置</Badge>
      ) : (
        <Badge variant="outline">自建</Badge>
      )}
    </div>

    {r.description && (
      <p className="mt-3 line-clamp-2 text-[12px] leading-snug text-stone-600">
        {r.description}
      </p>
    )}

    <div className="mt-3 inline-flex w-fit items-center gap-1 rounded-md bg-stone-100 px-2 py-0.5 font-mono text-[11px] text-stone-600">
      <ShieldCheck className="h-3 w-3" />
      {r.permission_codes.length} 项权限
    </div>

    <div className="mt-3 flex items-center justify-between border-t border-stone-100 pt-2.5">
      <button
        type="button"
        onClick={onPerms}
        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] text-stone-600 transition hover:bg-stone-100 hover:text-stone-900"
      >
        <ShieldCheck className="h-3.5 w-3.5" /> 权限
      </button>
      <button
        type="button"
        title={r.is_system ? '内置角色不可删' : '删除'}
        onClick={onDelete}
        disabled={r.is_system}
        className="rounded-md p-1 text-stone-400 opacity-0 transition group-hover:opacity-100 hover:bg-red-100 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  </div>
);

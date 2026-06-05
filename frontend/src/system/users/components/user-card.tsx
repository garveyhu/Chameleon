/** UserCard —— 单个用户的现代卡片（替代表格行）。 */

import { KeyRound, Trash2 } from 'lucide-react';

import { Badge } from '@/core/components/ui/badge';
import { StatusBadge } from '@/core/components/ui/status-badge';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import type { UserItem } from '@/system/users/types/user';

interface Props {
  user: UserItem;
  onReset: () => void;
  onDelete: () => void;
}

export const UserCard = ({ user: u, onReset, onDelete }: Props) => {
  const title = u.display_name || u.username;
  const active = u.status === 'active';
  const isAdmin = u.username === 'admin';

  return (
    <div
      className={cn(
        'group flex flex-col rounded-xl border border-stone-200 bg-[var(--color-paper)] p-4 transition hover:-translate-y-0.5 hover:shadow-pop',
        !active && 'opacity-65',
      )}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary-50 text-[15px] font-semibold text-primary-600">
          {title.slice(0, 1).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[14px] font-medium text-stone-900">{title}</div>
          <div className="truncate font-mono text-[11px] text-stone-400">
            @{u.username}
            {u.email ? ` · ${u.email}` : ''}
          </div>
        </div>
        {active ? (
          <StatusBadge tone="success">活跃</StatusBadge>
        ) : (
          <StatusBadge tone="neutral">停用</StatusBadge>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-1">
        {u.role_codes.length ? (
          u.role_codes.map(r => (
            <Badge key={r} variant="primary">
              {r}
            </Badge>
          ))
        ) : (
          <span className="text-[11px] text-stone-400">无角色</span>
        )}
      </div>

      <div className="mt-3 text-[11px] text-stone-400">
        最近登录 <span className="tnum font-mono">{formatDateTime(u.last_login_at)}</span>
      </div>

      <div className="mt-3 flex items-center justify-end gap-0.5 border-t border-stone-100 pt-2.5">
        <button
          type="button"
          onClick={onReset}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] text-stone-600 transition hover:bg-stone-100 hover:text-stone-900"
        >
          <KeyRound className="h-3.5 w-3.5" /> 重置密码
        </button>
        <button
          type="button"
          title={isAdmin ? '内置 admin 不可删' : '删除'}
          onClick={onDelete}
          disabled={isAdmin}
          className="rounded-md p-1 text-stone-400 opacity-0 transition group-hover:opacity-100 hover:bg-red-100 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
};

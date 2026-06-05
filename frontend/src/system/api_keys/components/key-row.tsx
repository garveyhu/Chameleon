/** KeyRow —— 单个 API Key 的密集列表行（替代卡片，一屏可容纳更多）。
 *
 * 作用域配色左描边 + 图标，name/作用域 + 掩码密钥(展开/复制) + 配额 + 最近使用 + 状态 + 撤销，
 * 单行排布。配合 apps-page 的 divide-y 容器。
 */

import { Check, Copy, Eye, EyeOff } from 'lucide-react';
import { useState } from 'react';

import { StatusBadge } from '@/core/components/ui/status-badge';
import { cn } from '@/core/lib/cn';
import { formatRelative } from '@/core/lib/format';
import { scopeMeta } from '@/system/api_keys/scope';
import type { ApiKeyItem } from '@/system/api_keys/types/app';

interface Props {
  apiKey: ApiKeyItem;
  onRevoke: () => void;
}

export const KeyRow = ({ apiKey: k, onRevoke }: Props) => {
  const meta = scopeMeta(k.scope_type);
  const Icon = meta.icon;
  const revoked = !!k.revoked_at;

  return (
    <div
      className={cn(
        'flex items-center gap-3 border-l-[3px] px-3 py-2.5 transition hover:bg-stone-50',
        meta.accent,
        revoked && 'opacity-55',
      )}
    >
      <div className="flex w-52 shrink-0 items-center gap-2.5">
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

      <div className="min-w-0 flex-1">
        <KeyCopyCell prefix={k.key_prefix} plain={k.plain_key} />
      </div>

      <div
        className="hidden w-28 shrink-0 text-right font-mono text-[11px] text-stone-500 lg:block"
        title="QPM / QPD 限额"
      >
        {k.qpm_limit ?? '∞'} <span className="text-stone-300">/</span> {k.qpd_limit ?? '∞'}
      </div>

      <div className="hidden w-20 shrink-0 text-right text-[11px] text-stone-400 md:block">
        {k.last_used_at ? formatRelative(k.last_used_at) : '从未'}
      </div>

      <div className="w-[68px] shrink-0">
        {revoked ? (
          <StatusBadge tone="error">已撤销</StatusBadge>
        ) : (
          <StatusBadge tone="success">活跃</StatusBadge>
        )}
      </div>

      <div className="w-12 shrink-0 text-right">
        {!revoked && (
          <button
            type="button"
            onClick={onRevoke}
            className="rounded px-1.5 py-0.5 text-[11px] text-red-600 transition hover:bg-red-50"
          >
            撤销
          </button>
        )}
      </div>
    </div>
  );
};

/** 密钥单元格：默认掩码，点眼睛展开全文，点复制拷全文（老数据无明文只显前缀）。 */
export const KeyCopyCell = ({ prefix, plain }: { prefix: string; plain: string | null }) => {
  const [shown, setShown] = useState(false);
  const [copied, setCopied] = useState(false);
  const copy = () => {
    if (!plain) return;
    void navigator.clipboard.writeText(plain).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="flex items-center gap-1.5">
      <code className="min-w-0 flex-1 truncate font-mono text-[12px] text-stone-600">
        {plain ? (shown ? plain : `${prefix}${'•'.repeat(8)}`) : `${prefix}...`}
      </code>
      {plain && (
        <>
          <button
            type="button"
            onClick={() => setShown(s => !s)}
            title={shown ? '隐藏' : '显示'}
            className="shrink-0 text-stone-400 transition hover:text-stone-700"
          >
            {shown ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
          <button
            type="button"
            onClick={copy}
            title="复制"
            className="shrink-0 text-stone-400 transition hover:text-stone-700"
          >
            {copied ? (
              <Check className="h-3.5 w-3.5 text-emerald-500" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </button>
        </>
      )}
    </div>
  );
};

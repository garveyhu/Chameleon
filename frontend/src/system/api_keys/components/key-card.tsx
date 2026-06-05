/** KeyCard —— 单个 API Key 的现代卡片。
 *
 * 取代密钥表格行：作用域配色左描边 + 图标 + 掩码密钥(可展开/复制) + 配额 + 状态 + 撤销。
 */

import { Check, Copy, Eye, EyeOff } from 'lucide-react';
import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/core/components/ui/button';
import { StatusBadge } from '@/core/components/ui/status-badge';
import { cn } from '@/core/lib/cn';
import { formatRelative } from '@/core/lib/format';
import { scopeMeta } from '@/system/api_keys/scope';
import type { ApiKeyItem } from '@/system/api_keys/types/app';

const Fact = ({ label, children }: { label: string; children: ReactNode }) => (
  <div className="min-w-0">
    <div className="text-[10px] tracking-wide text-stone-400 uppercase">{label}</div>
    <div className="mt-0.5 truncate text-[12px] text-stone-700">{children}</div>
  </div>
);

interface Props {
  apiKey: ApiKeyItem;
  onRevoke: () => void;
}

export const KeyCard = ({ apiKey: k, onRevoke }: Props) => {
  const meta = scopeMeta(k.scope_type);
  const Icon = meta.icon;
  const revoked = !!k.revoked_at;

  return (
    <div
      className={cn(
        'flex flex-col rounded-xl border border-l-[3px] border-stone-200 bg-[var(--color-paper)] p-4 transition hover:-translate-y-0.5 hover:shadow-pop',
        meta.accent,
        revoked && 'opacity-60',
      )}
    >
      <div className="flex items-start gap-2.5">
        <div className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-lg', meta.chip)}>
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13.5px] font-medium text-stone-900">{k.name}</div>
          <span
            className={cn(
              'mt-0.5 inline-flex rounded px-1.5 py-0.5 text-[10.5px] font-medium',
              meta.chip,
            )}
          >
            {meta.label}
          </span>
        </div>
        {revoked ? (
          <StatusBadge tone="error">已撤销</StatusBadge>
        ) : (
          <StatusBadge tone="success">活跃</StatusBadge>
        )}
      </div>

      <div className="mt-3 rounded-lg bg-stone-50 px-2.5 py-1.5">
        <KeyCopyCell prefix={k.key_prefix} plain={k.plain_key} />
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2.5">
        <Fact label="目标">
          {k.scope_ref ? (
            <span className="font-mono text-[11.5px]">{k.scope_ref}</span>
          ) : (
            <span className="text-stone-300">—</span>
          )}
        </Fact>
        <Fact label="最近使用">{k.last_used_at ? formatRelative(k.last_used_at) : '从未'}</Fact>
        <Fact label="配额">
          <span className="tnum font-mono text-[11.5px] text-stone-500">
            {k.qpm_limit ?? '∞'} QPM · {k.qpd_limit ?? '∞'} QPD
          </span>
        </Fact>
        <Fact label="来源">
          <span className="font-mono text-[11px] text-stone-400">{k.app_id}</span>
        </Fact>
      </div>

      {!revoked && (
        <div className="mt-3 flex justify-end border-t border-stone-100 pt-2.5">
          <Button size="sm" variant="ghost" className="text-red-600" onClick={onRevoke}>
            撤销
          </Button>
        </div>
      )}
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
      <code className="flex-1 truncate font-mono text-[12px] text-stone-600">
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

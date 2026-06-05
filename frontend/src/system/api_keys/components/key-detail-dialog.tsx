/** KeyDetailDialog —— 点击列表行弹出的密钥详情。
 *
 * 列表外不暴露密钥；只有在此弹窗里可预览(显示/隐藏)与复制明文，并可撤销。
 */

import { Ban, Check, Copy, Eye, EyeOff } from 'lucide-react';
import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/core/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/core/components/ui/dialog';
import { cn } from '@/core/lib/cn';
import { formatDateTime, formatRelative } from '@/core/lib/format';
import { scopeMeta } from '@/system/api_keys/scope';
import type { ApiKeyItem } from '@/system/api_keys/types/app';

interface Props {
  apiKey: ApiKeyItem | null;
  onClose: () => void;
  onRevoke: () => void;
}

const Fact = ({ label, children }: { label: string; children: ReactNode }) => (
  <div className="min-w-0">
    <div className="text-[10px] tracking-wide text-stone-400 uppercase">{label}</div>
    <div className="mt-0.5 truncate text-[12.5px] text-stone-700">{children}</div>
  </div>
);

export const KeyDetailDialog = ({ apiKey, onClose, onRevoke }: Props) => (
  <Dialog open={!!apiKey} onOpenChange={o => !o && onClose()}>
    <DialogContent>
      {apiKey && <Body key={String(apiKey.id)} k={apiKey} onRevoke={onRevoke} />}
    </DialogContent>
  </Dialog>
);

const Body = ({ k, onRevoke }: { k: ApiKeyItem; onRevoke: () => void }) => {
  const meta = scopeMeta(k.scope_type);
  const [shown, setShown] = useState(false);
  const [copied, setCopied] = useState(false);
  const copy = () => {
    if (!k.plain_key) return;
    void navigator.clipboard.writeText(k.plain_key).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <span className={cn('inline-flex rounded px-1.5 py-0.5 text-[11px] font-medium', meta.chip)}>
            {meta.label}
          </span>
          {k.name}
        </DialogTitle>
        <DialogDescription>密钥详情 —— 仅此处可预览与复制明文</DialogDescription>
      </DialogHeader>

      <div className="bg-warm-2/40 overflow-hidden rounded-lg border border-stone-200/80">
        <div className="flex items-center justify-between border-b border-stone-200/70 bg-white/40 px-3 py-1.5">
          <span className="text-[11.5px] font-medium text-stone-700">API Key（明文）</span>
          {k.plain_key && (
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setShown(s => !s)}
                className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-stone-500 transition hover:bg-stone-100 hover:text-stone-900"
              >
                {shown ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                {shown ? '隐藏' : '显示'}
              </button>
              <button
                type="button"
                onClick={copy}
                className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-stone-500 transition hover:bg-stone-100 hover:text-stone-900"
              >
                {copied ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
                {copied ? '已复制' : '复制'}
              </button>
            </div>
          )}
        </div>
        <pre className="overflow-x-auto px-3.5 py-3 font-mono text-[12.5px] leading-relaxed break-all whitespace-pre-wrap text-stone-800">
          {k.plain_key
            ? shown
              ? k.plain_key
              : `${k.key_prefix}${'•'.repeat(24)}`
            : `${k.key_prefix}…（旧数据未留存明文）`}
        </pre>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3">
        <Fact label="作用域">{meta.label}</Fact>
        <Fact label="目标">{k.scope_ref || '—'}</Fact>
        <Fact label="来源标签">
          <span className="font-mono text-[11.5px]">{k.app_id}</span>
        </Fact>
        <Fact label="最近使用">{k.last_used_at ? formatRelative(k.last_used_at) : '从未使用'}</Fact>
        <Fact label="创建时间">
          <span className="tnum font-mono text-[11.5px]">{formatDateTime(k.created_at)}</span>
        </Fact>
        {k.description && (
          <div className="col-span-2">
            <div className="text-[10px] tracking-wide text-stone-400 uppercase">描述</div>
            <div className="mt-0.5 text-[12.5px] leading-snug text-stone-700">{k.description}</div>
          </div>
        )}
      </div>

      <DialogFooter>
        <Button variant="outline" className="text-red-600" onClick={onRevoke}>
          <Ban className="h-4 w-4" /> 撤销密钥
        </Button>
      </DialogFooter>
    </>
  );
};

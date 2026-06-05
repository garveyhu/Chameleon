/** KeyDetailDialog —— 点击列表行弹出的密钥详情。
 *
 * 名称与描述可在此编辑保存；密钥明文仅此处可预览(显示/隐藏)与复制，并可撤销。
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
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
import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { formatDateTime, formatRelative } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import { scopeMeta } from '@/system/api_keys/scope';
import { apiKeyApi } from '@/system/api_keys/services/app';
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
  const qc = useQueryClient();
  const [shown, setShown] = useState(false);
  const [copied, setCopied] = useState(false);
  const [baseName, setBaseName] = useState(k.name);
  const [baseDesc, setBaseDesc] = useState(k.description ?? '');
  const [name, setName] = useState(k.name);
  const [desc, setDesc] = useState(k.description ?? '');

  const dirty = name.trim() !== baseName || desc.trim() !== baseDesc;
  const canSave = dirty && name.trim().length > 0;

  const saveMut = useMutation({
    mutationFn: () =>
      apiKeyApi.update(k.id, { name: name.trim(), description: desc.trim() }),
    onSuccess: () => {
      toast.success('已保存');
      setBaseName(name.trim());
      setBaseDesc(desc.trim());
      qc.invalidateQueries({ queryKey: ['api-keys'] });
      qc.invalidateQueries({ queryKey: ['api-keys-stats'] });
    },
  });

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
          {name.trim() || k.name}
        </DialogTitle>
        <DialogDescription>名称与描述可编辑 —— 密钥仅此处可预览与复制</DialogDescription>
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

      <div className="mt-4 space-y-3">
        <div className="space-y-1">
          <Label className="text-[11px] text-stone-500">名称</Label>
          <Input value={name} onChange={e => setName(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label className="text-[11px] text-stone-500">描述</Label>
          <Textarea
            value={desc}
            onChange={e => setDesc(e.target.value)}
            rows={2}
            placeholder="给这个密钥加点说明…"
          />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-stone-100 pt-4">
        <Fact label="作用域">{meta.label}</Fact>
        <Fact label="目标">{k.scope_ref || '—'}</Fact>
        <Fact label="来源标签">
          <span className="font-mono text-[11.5px]">{k.app_id}</span>
        </Fact>
        <Fact label="最近使用">{k.last_used_at ? formatRelative(k.last_used_at) : '从未使用'}</Fact>
        <Fact label="创建时间">
          <span className="tnum font-mono text-[11.5px]">{formatDateTime(k.created_at)}</span>
        </Fact>
      </div>

      <DialogFooter className="items-center">
        <Button variant="outline" className="mr-auto text-red-600" onClick={onRevoke}>
          <Ban className="h-4 w-4" /> 撤销密钥
        </Button>
        <Button variant="primary" disabled={!canSave || saveMut.isPending} onClick={() => saveMut.mutate()}>
          {saveMut.isPending ? '保存中…' : '保存'}
        </Button>
      </DialogFooter>
    </>
  );
};

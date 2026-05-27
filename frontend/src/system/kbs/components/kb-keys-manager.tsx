/** 知识库密钥管理面板（新建 + 列表 + 掩码/复制）—— 可复用
 *
 * 被「服务 API 弹窗」与「API 文档页 → 管理密钥」共用，避免密钥表三处重复。
 * 密钥为 KB 作用域（kbs- 前缀），仅对该 KB 公开 API /v1/kbs/{kb_key}/* 有效。
 */
import { useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Copy, Eye, EyeOff, Plus } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { kbApi } from '@/system/kbs/services/kb';
import type { KbApiKey } from '@/system/kbs/types/kb';

interface Props {
  kbId: EntityId;
}

export const KbKeysManager = ({ kbId }: Props) => {
  const qc = useQueryClient();
  const [name, setName] = useState('');
  const [confirmId, setConfirmId] = useState<EntityId | null>(null);

  const listQ = useQuery({
    queryKey: ['kb-api-keys', kbId],
    queryFn: () => kbApi.listKeys(kbId),
  });

  const createMut = useMutation({
    mutationFn: () => kbApi.createKey(kbId, name.trim()),
    onSuccess: () => {
      setName('');
      toast.success('已生成');
      void qc.invalidateQueries({ queryKey: ['kb-api-keys', kbId] });
    },
    onError: e => toast.error((e as Error).message),
  });

  const revokeMut = useMutation({
    mutationFn: (keyId: EntityId) => kbApi.revokeKey(kbId, keyId),
    onSuccess: () => {
      setConfirmId(null);
      toast.success('已删除');
      void qc.invalidateQueries({ queryKey: ['kb-api-keys', kbId] });
    },
    onError: e => toast.error((e as Error).message),
  });

  const keys = listQ.data ?? [];

  return (
    <div className="space-y-4">
      {/* 新建密钥 */}
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <label className="mb-1 block text-[12px] text-stone-600">
            新建密钥（kbs- 前缀，仅对本知识库有效）
          </label>
          <Input
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="密钥名称（如：生产环境）"
            className="h-8"
          />
        </div>
        <Button size="sm" onClick={() => createMut.mutate()} disabled={createMut.isPending}>
          <Plus className="mr-1 h-3.5 w-3.5" />
          生成
        </Button>
      </div>

      {/* 密钥列表 */}
      <div className="overflow-hidden rounded-lg border border-stone-200">
        <table className="w-full text-[12px]">
          <thead className="bg-stone-50 text-[11px] text-stone-500">
            <tr>
              <th className="px-3 py-2 text-left font-medium">名称</th>
              <th className="px-3 py-2 text-left font-medium">密钥</th>
              <th className="px-3 py-2 text-left font-medium">最近使用</th>
              <th className="px-3 py-2 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {keys.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-stone-400">
                  {listQ.isLoading ? '加载中…' : '暂无密钥，点上方「生成」创建'}
                </td>
              </tr>
            )}
            {keys.map(k => (
              <tr key={String(k.id)} className="border-t border-stone-100">
                <td className="px-3 py-2 text-stone-800">{k.name}</td>
                <td className="px-3 py-2">
                  <KeyCell k={k} />
                </td>
                <td className="px-3 py-2 text-stone-500">
                  {k.last_used_at ? formatDateTime(k.last_used_at) : '从未'}
                </td>
                <td className="px-3 py-2 text-right">
                  {confirmId === k.id ? (
                    <span className="inline-flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => revokeMut.mutate(k.id)}
                        disabled={revokeMut.isPending}
                        className="rounded bg-rose-600 px-2 py-0.5 text-[11px] text-white hover:bg-rose-700 disabled:opacity-50"
                      >
                        确认删除
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmId(null)}
                        className="rounded px-2 py-0.5 text-[11px] text-stone-500 hover:bg-stone-100"
                      >
                        取消
                      </button>
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirmId(k.id)}
                      className="rounded px-2 py-0.5 text-[11px] text-rose-600 hover:bg-rose-50"
                    >
                      删除
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

/** 密钥单元格：默认掩码，点眼睛展开全文，点复制拷全文（老数据无明文则只显前缀） */
const KeyCell = ({ k }: { k: KbApiKey }) => {
  const [shown, setShown] = useState(false);
  const [copied, setCopied] = useState(false);
  const full = k.plain_key;

  const copy = () => {
    if (!full) return;
    void navigator.clipboard.writeText(full).then(() => {
      setCopied(true);
      toast.success('已复制');
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div className="flex items-center gap-1.5">
      <code className="font-mono text-[11px] text-stone-600">
        {full ? (shown ? full : `${k.key_prefix}${'•'.repeat(8)}`) : `${k.key_prefix}…`}
      </code>
      {full && (
        <>
          <button
            type="button"
            onClick={() => setShown(s => !s)}
            title={shown ? '隐藏' : '显示'}
            className="text-stone-400 transition hover:text-stone-700"
          >
            {shown ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
          <button
            type="button"
            onClick={copy}
            title="复制"
            className="text-stone-400 transition hover:text-stone-700"
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

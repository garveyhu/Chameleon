/** 应用密钥面板 —— 列出 / 新建 / 吊销某应用（智能体）的专属 API Key
 *
 * 与系统应用密钥不同：这里生成的密钥作用域为该应用（scope_type='app'，scope_ref=agent_key），
 * 仅对该应用的 invoke / chat completions 端点有效。明文留存，可随时展开 / 复制（老数据无明文只能看前缀）。
 *
 * 入口可参数化：图编辑器按 graph_id 注入、应用详情页按 agent_id 注入，复用同一展示与交互。
 */
import { useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Copy, Eye, EyeOff, Plus, ShieldCheck } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';

export interface AppKey {
  id: EntityId;
  name: string;
  key_prefix: string;
  plain_key: string | null;
  last_used_at: string | null;
}

interface KeysApi {
  list: () => Promise<AppKey[]>;
  create: (name: string) => Promise<AppKey>;
  revoke: (keyId: EntityId) => Promise<unknown>;
}

interface Props {
  /** react-query 缓存命名空间（如 ['agent-api-keys', agentId]） */
  queryKey: readonly unknown[];
  keysApi: KeysApi;
}

export const AppKeysPanel = ({ queryKey, keysApi }: Props) => {
  const qc = useQueryClient();
  const [name, setName] = useState('');
  const [confirmId, setConfirmId] = useState<EntityId | null>(null);

  const listQ = useQuery({ queryKey, queryFn: keysApi.list });

  const createMut = useMutation({
    mutationFn: () => keysApi.create(name.trim()),
    onSuccess: () => {
      setName('');
      toast.success('已生成');
      void qc.invalidateQueries({ queryKey });
    },
    onError: e => toast.error((e as Error).message),
  });

  const revokeMut = useMutation({
    mutationFn: (keyId: EntityId) => keysApi.revoke(keyId),
    onSuccess: () => {
      setConfirmId(null);
      toast.success('已删除');
      void qc.invalidateQueries({ queryKey });
    },
    onError: e => toast.error((e as Error).message),
  });

  const listErr = listQ.error as Error | null;
  const keys = listQ.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2 rounded-lg border border-sky-100 bg-sky-50/60 px-3 py-2 text-[11.5px] leading-relaxed text-sky-800">
        <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sky-500" />
        <span>
          此处生成的密钥<strong>仅对本应用有效</strong>（调用其 invoke / chat
          completions）；与「应用密钥」不同，全局应用密钥默认对所有系统端点有效。
        </span>
      </div>

      {listErr ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-[12px] text-amber-700">
          {listErr.message}
        </div>
      ) : (
        <>
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <label className="mb-1 block text-[12px] text-stone-600">新建密钥</label>
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
        </>
      )}
    </div>
  );
};

/** 密钥单元格：默认掩码，点眼睛展开全文，点复制拷全文（老数据无明文则只显前缀） */
const KeyCell = ({ k }: { k: AppKey }) => {
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

/** Plugin Marketplace 页 —— 注册 registry + 浏览 + 一键装
 *
 * 整体布局：
 *  - Header：标题 + 「添加 registry」按钮 + 搜索框
 *  - registries section：已配置的 marketplace 列表 + 同步/启停/删除
 *  - entries grid：搜索结果 plugin 卡片 + install 按钮
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Plus,
  RefreshCw,
  Search,
  ShoppingBag,
  Trash2,
} from 'lucide-react';
import { useMemo, useState } from 'react';

import { SectionCard } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { cn } from '@/core/lib/cn';
import { confirm } from '@/core/lib/confirm';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import { AddRegistryModal } from '@/system/marketplace/components/add-registry-modal';
import { marketplaceApi } from '@/system/marketplace/services/marketplace';
import type {
  AddRegistryPayload,
  MarketplaceEntry,
} from '@/system/marketplace/types/marketplace';

const TYPE_COLOR: Record<string, string> = {
  provider: 'bg-sky-50 text-sky-700',
  tool: 'bg-violet-50 text-violet-700',
  embedding: 'bg-amber-50 text-amber-700',
};

export const MarketplacePage = () => {
  const qc = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [query, setQuery] = useState('');

  const regsQ = useQuery({
    queryKey: ['marketplace-registries'],
    queryFn: marketplaceApi.listRegistries,
  });

  const searchQ = useQuery({
    queryKey: ['marketplace-search', query],
    queryFn: () => marketplaceApi.search(query),
    staleTime: 10_000,
  });

  const addMut = useMutation({
    mutationFn: (p: AddRegistryPayload) => marketplaceApi.addRegistry(p),
    onSuccess: r => {
      toast.success(`已添加 ${r.name}`);
      qc.invalidateQueries({ queryKey: ['marketplace-registries'] });
      setAddOpen(false);
    },
    onError: (e: unknown) => {
      toast.error((e as { message?: string })?.message || '添加失败');
    },
  });

  const syncMut = useMutation({
    mutationFn: (id: string | number) => marketplaceApi.syncRegistry(id),
    onSuccess: r => {
      toast.success(`同步完成 · ${r.entries} 个 plugin · ${r.publishers} 个 publisher`);
      qc.invalidateQueries({ queryKey: ['marketplace-registries'] });
      qc.invalidateQueries({ queryKey: ['marketplace-search'] });
    },
    onError: (e: unknown) => {
      toast.error((e as { message?: string })?.message || '同步失败');
    },
  });

  const toggleMut = useMutation({
    mutationFn: (args: { id: string | number; enabled: boolean }) =>
      marketplaceApi.updateRegistry(args.id, { enabled: args.enabled }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketplace-registries'] });
      qc.invalidateQueries({ queryKey: ['marketplace-search'] });
    },
  });

  const delMut = useMutation({
    mutationFn: (id: string | number) => marketplaceApi.deleteRegistry(id),
    onSuccess: () => {
      toast.success('已删除 registry');
      qc.invalidateQueries({ queryKey: ['marketplace-registries'] });
      qc.invalidateQueries({ queryKey: ['marketplace-search'] });
    },
  });

  const installMut = useMutation({
    mutationFn: (args: { registry_id: string | number; plugin_name: string }) =>
      marketplaceApi.install(args),
    onSuccess: r => {
      toast.success(`已装 ${r.plugin_key} · publisher=${r.publisher}`);
      qc.invalidateQueries({ queryKey: ['marketplace-search'] });
      qc.invalidateQueries({ queryKey: ['plugins'] });
    },
    onError: (e: unknown) => {
      toast.error((e as { message?: string })?.message || '安装失败');
    },
  });

  const registries = regsQ.data ?? [];
  const entries = searchQ.data ?? [];

  const totalEntries = useMemo(() => {
    return registries.reduce(
      (sum, r) => sum + (r.last_synced_at ? 1 : 0),
      0,
    );
  }, [registries]);

  return (
    <>
      <div className="space-y-3">
        <SectionCard>
          <header className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="flex items-center gap-1.5 text-[14px] font-medium text-stone-900">
                <ShoppingBag className="h-4 w-4 text-stone-500" />
                插件市场
              </h2>
              <p className="mt-0.5 text-[11.5px] text-stone-500">
                远端 plugin marketplace + Ed25519 签名验证 + 一键安装
              </p>
            </div>
            <Button size="sm" onClick={() => setAddOpen(true)}>
              <Plus className="mr-1 h-3 w-3" />
              添加 registry
            </Button>
          </header>

          {regsQ.isLoading ? (
            <div className="py-8 text-center text-[12px] text-stone-400">
              加载中…
            </div>
          ) : registries.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-stone-400">
              还没有 registry；点右上"添加 registry"开始
            </div>
          ) : (
            <table className="w-full text-[12.5px]">
              <thead className="text-[11px] uppercase tracking-wider text-stone-500">
                <tr>
                  <th className="px-2 py-1.5 text-left">名称</th>
                  <th className="px-2 py-1.5 text-left">URL</th>
                  <th className="px-2 py-1.5 text-left">上次同步</th>
                  <th className="px-2 py-1.5 text-left">状态</th>
                  <th className="px-2 py-1.5 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {registries.map(r => (
                  <tr
                    key={String(r.id)}
                    className="border-t border-stone-200/70"
                  >
                    <td className="px-2 py-1.5 text-stone-800">{r.name}</td>
                    <td className="px-2 py-1.5 font-mono text-[11px] text-stone-600">
                      {r.registry_url}
                    </td>
                    <td className="px-2 py-1.5 font-mono text-[11px] text-stone-500">
                      {r.last_synced_at
                        ? formatDateTime(r.last_synced_at)
                        : '未同步'}
                    </td>
                    <td className="px-2 py-1.5">
                      <Badge
                        variant="outline"
                        className={cn(
                          'text-[10.5px]',
                          r.enabled
                            ? 'bg-emerald-50 text-emerald-700'
                            : 'bg-stone-50 text-stone-500',
                        )}
                      >
                        {r.enabled ? '启用' : '禁用'}
                      </Badge>
                    </td>
                    <td className="px-2 py-1.5 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button"
                          title="同步 index.json"
                          disabled={!r.enabled || syncMut.isPending}
                          onClick={() => syncMut.mutate(r.id)}
                          className="rounded p-1 text-stone-400 hover:bg-primary-50 hover:text-primary-700 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            toggleMut.mutate({
                              id: r.id,
                              enabled: !r.enabled,
                            })
                          }
                          className={cn(
                            'rounded px-2 py-0.5 text-[10.5px] font-medium',
                            r.enabled
                              ? 'bg-stone-50 text-stone-600 hover:bg-stone-200'
                              : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100',
                          )}
                        >
                          {r.enabled ? 'OFF' : 'ON'}
                        </button>
                        <button
                          type="button"
                          title="删除"
                          onClick={async () => {
                            if (
                              await confirm({
                                title: '确认删除？',
                                description: `marketplace ${r.name} 将被移除（已安装的 plugin 不受影响）`,
                              })
                            ) {
                              delMut.mutate(r.id);
                            }
                          }}
                          className="rounded p-1 text-stone-400 hover:bg-rose-50 hover:text-rose-600"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </SectionCard>

        <SectionCard>
          <header className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="text-[13px] font-medium text-stone-800">
                浏览插件
              </h3>
              <p className="mt-0.5 text-[11px] text-stone-500">
                跨所有 enabled registry 缓存搜索（未同步的 registry 不显）·
                {' '}
                {totalEntries} 个已同步
              </p>
            </div>
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-stone-400" />
              <Input
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="按 name / description 搜索…"
                className="w-[260px] pl-8 text-[12px]"
              />
            </div>
          </header>

          {searchQ.isLoading ? (
            <div className="py-8 text-center text-[12px] text-stone-400">
              搜索中…
            </div>
          ) : entries.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-stone-400">
              {query
                ? '未找到匹配的插件'
                : '没有可浏览的插件；先添加 registry + 同步'}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
              {entries.map(entry => (
                <EntryCard
                  key={`${entry.registry_id}:${entry.name}`}
                  entry={entry}
                  busy={installMut.isPending}
                  onInstall={() =>
                    installMut.mutate({
                      registry_id: entry.registry_id,
                      plugin_name: entry.name,
                    })
                  }
                />
              ))}
            </div>
          )}
        </SectionCard>
      </div>

      <AddRegistryModal
        open={addOpen}
        loading={addMut.isPending}
        onClose={() => setAddOpen(false)}
        onSubmit={p => addMut.mutate(p)}
      />
    </>
  );
};

// ── 卡片 ─────────────────────────────────────────────


interface EntryCardProps {
  entry: MarketplaceEntry;
  busy: boolean;
  onInstall: () => void;
}

const EntryCard: React.FC<EntryCardProps> = ({ entry, busy, onInstall }) => (
  <div className="flex flex-col gap-2 rounded-md border border-stone-200/70 bg-white p-3 transition hover:border-amber-300 hover:bg-amber-50/40">
    <div className="flex items-start justify-between gap-2">
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-[13px] font-medium text-stone-900">
            {entry.name}
          </span>
          <Badge
            variant="outline"
            className={cn(
              'flex-shrink-0 text-[10px]',
              TYPE_COLOR[entry.type] ?? 'bg-stone-50 text-stone-600',
            )}
          >
            {entry.type}
          </Badge>
        </div>
        <div className="mt-0.5 font-mono text-[10.5px] text-stone-500">
          v{entry.latest} · publisher {entry.publisher}
        </div>
      </div>
      {entry.installed ? (
        <Badge
          variant="outline"
          className="bg-emerald-50 text-[10.5px] text-emerald-700"
        >
          已安装
        </Badge>
      ) : (
        <Button size="sm" disabled={busy} onClick={onInstall}>
          安装
        </Button>
      )}
    </div>
    <p className="text-[11.5px] text-stone-600 line-clamp-2">
      {entry.description || '— 无描述 —'}
    </p>
    <div className="flex flex-wrap items-center gap-1">
      {entry.tags.map(t => (
        <span
          key={t}
          className="rounded-full bg-stone-100 px-1.5 py-0.5 text-[10px] text-stone-600"
        >
          {t}
        </span>
      ))}
      <span className="ml-auto text-[10.5px] text-stone-400">
        {entry.downloads.toLocaleString()} 下载
      </span>
    </div>
  </div>
);

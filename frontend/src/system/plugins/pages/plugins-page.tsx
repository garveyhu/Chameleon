/** Plugins 管理页 —— builtin + 已安装 + 操作（enable/disable/reload/uninstall/config）*/

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Puzzle, RefreshCw, Settings, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';

import { SectionCard } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { cn } from '@/core/lib/cn';
import { confirm } from '@/core/lib/confirm';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import { PluginConfigModal } from '@/system/plugins/components/plugin-config-modal';
import { PluginInstallModal } from '@/system/plugins/components/plugin-install-modal';
import { pluginApi } from '@/system/plugins/services/plugin';
import type { PluginInstanceItem } from '@/system/plugins/types/plugin';

const TYPE_LABEL: Record<string, string> = {
  provider: 'Provider',
  tool: 'Tool',
  embedding: 'Embedding',
};

const TYPE_COLOR: Record<string, string> = {
  provider: 'bg-sky-50 text-sky-700',
  tool: 'bg-violet-50 text-violet-700',
  embedding: 'bg-amber-50 text-amber-700',
};

export const PluginsPage = () => {
  const qc = useQueryClient();
  const [installOpen, setInstallOpen] = useState(false);
  const [configTarget, setConfigTarget] = useState<PluginInstanceItem | null>(
    null,
  );

  const listQ = useQuery({
    queryKey: ['plugins'],
    queryFn: () => pluginApi.list(),
  });

  const installMut = useMutation({
    mutationFn: pluginApi.install,
    onSuccess: i => {
      toast.success(`已安装：${i.plugin_key}`);
      qc.invalidateQueries({ queryKey: ['plugins'] });
      setInstallOpen(false);
    },
    onError: (e: unknown) => {
      toast.error((e as { message?: string })?.message || '安装失败');
    },
  });

  const toggleMut = useMutation({
    mutationFn: (args: { id: string | number; enabled: boolean }) =>
      args.enabled
        ? pluginApi.enable(args.id)
        : pluginApi.disable(args.id),
    onSuccess: r => {
      const verb = r.enabled ? '已启用' : '已禁用';
      const note = r.loaded === false && r.enabled ? '（加载失败）' : '';
      toast.success(`${verb} ${r.plugin_key} ${note}`);
      qc.invalidateQueries({ queryKey: ['plugins'] });
    },
    onError: (e: unknown) => {
      toast.error((e as { message?: string })?.message || '切换失败');
    },
  });

  const reloadMut = useMutation({
    mutationFn: (id: string | number) => pluginApi.reload(id),
    onSuccess: r => {
      toast.success(
        r.loaded
          ? `已 reload ${r.plugin_key}`
          : `reload 未生效（${r.message ?? '已禁用?'}）`,
      );
      qc.invalidateQueries({ queryKey: ['plugins'] });
    },
    onError: (e: unknown) => {
      toast.error((e as { message?: string })?.message || 'reload 失败');
    },
  });

  const delMut = useMutation({
    mutationFn: (id: string | number) => pluginApi.uninstall(id),
    onSuccess: () => {
      toast.success('已卸载');
      qc.invalidateQueries({ queryKey: ['plugins'] });
    },
    onError: (e: unknown) => {
      toast.error((e as { message?: string })?.message || '卸载失败');
    },
  });

  const configMut = useMutation({
    mutationFn: (args: {
      id: string | number;
      config: Record<string, unknown>;
    }) => pluginApi.updateConfig(args.id, args.config),
    onSuccess: () => {
      toast.success('config 已保存');
      qc.invalidateQueries({ queryKey: ['plugins'] });
      setConfigTarget(null);
    },
    onError: (e: unknown) => {
      toast.error((e as { message?: string })?.message || '保存失败');
    },
  });

  const grouped = useMemo(() => {
    const rows = listQ.data ?? [];
    const builtin = rows.filter(r => r.source === 'builtin');
    const external = rows.filter(r => r.source !== 'builtin');
    return { builtin, external };
  }, [listQ.data]);

  return (
    <>
      <SectionCard>
        <header className="mb-3 flex items-center justify-between">
          <div>
            <h2 className="flex items-center gap-1.5 text-[14px] font-medium text-stone-900">
              <Puzzle className="h-4 w-4 text-stone-500" />
              插件
            </h2>
            <p className="mt-0.5 text-[11.5px] text-stone-500">
              扩展 Chameleon 的 Provider / Tool / Embedding；
              builtin 可 disable 但不可卸载，外部插件支持热加载
            </p>
          </div>
          <Button size="sm" onClick={() => setInstallOpen(true)}>
            <Plus className="mr-1 h-3 w-3" />
            安装插件
          </Button>
        </header>

        {listQ.isLoading ? (
          <div className="py-12 text-center text-[12px] text-stone-400">
            加载中…
          </div>
        ) : (
          <div className="space-y-5">
            <PluginSection
              title="内置插件"
              hint="Chameleon 自带；不可卸载，可禁用以从 PROVIDERS 注册表下架"
              rows={grouped.builtin}
              onToggle={(id, enabled) => toggleMut.mutate({ id, enabled })}
              onReload={id => reloadMut.mutate(id)}
              onUninstall={null}
              onConfig={p => setConfigTarget(p)}
              busy={toggleMut.isPending || reloadMut.isPending}
            />
            <PluginSection
              title="外部插件"
              hint="通过 install 端点注册；可热加载 / 卸载"
              rows={grouped.external}
              empty={`还没有外部插件；点右上"安装插件"添加`}
              onToggle={(id, enabled) => toggleMut.mutate({ id, enabled })}
              onReload={id => reloadMut.mutate(id)}
              onUninstall={async (id, key) => {
                if (
                  await confirm({
                    title: '确认卸载？',
                    description: `插件 ${key} 将被移除；已配置的 config 一并清空。`,
                  })
                ) {
                  delMut.mutate(id);
                }
              }}
              onConfig={p => setConfigTarget(p)}
              busy={
                toggleMut.isPending || reloadMut.isPending || delMut.isPending
              }
            />
          </div>
        )}
      </SectionCard>

      <PluginInstallModal
        open={installOpen}
        loading={installMut.isPending}
        onClose={() => setInstallOpen(false)}
        onSubmit={p => installMut.mutate(p)}
      />
      <PluginConfigModal
        open={!!configTarget}
        plugin={configTarget}
        loading={configMut.isPending}
        onClose={() => setConfigTarget(null)}
        onSubmit={config =>
          configTarget &&
          configMut.mutate({ id: configTarget.id, config })
        }
      />
    </>
  );
};

// ── 分组列表 ────────────────────────────────────────────

interface PluginSectionProps {
  title: string;
  hint?: string;
  rows: PluginInstanceItem[];
  empty?: string;
  onToggle: (id: string | number, enabled: boolean) => void;
  onReload: (id: string | number) => void;
  onUninstall: ((id: string | number, key: string) => void) | null;
  onConfig: (plugin: PluginInstanceItem) => void;
  busy: boolean;
}

const PluginSection: React.FC<PluginSectionProps> = ({
  title,
  hint,
  rows,
  empty,
  onToggle,
  onReload,
  onUninstall,
  onConfig,
  busy,
}) => (
  <section>
    <div className="mb-1.5 flex items-baseline gap-2">
      <h3 className="text-[12.5px] font-medium text-stone-800">{title}</h3>
      {hint && (
        <span className="text-[10.5px] text-stone-400">— {hint}</span>
      )}
      <span className="ml-auto text-[10.5px] text-stone-400">
        {rows.length} 条
      </span>
    </div>
    {rows.length === 0 ? (
      <div className="py-8 text-center text-[11.5px] text-stone-400">
        {empty ?? '—'}
      </div>
    ) : (
      <table className="w-full text-[12px]">
        <thead className="text-[10.5px] uppercase tracking-wider text-stone-500">
          <tr>
            <th className="px-2 py-1.5 text-left">plugin_key</th>
            <th className="px-2 py-1.5 text-left">类型</th>
            <th className="px-2 py-1.5 text-left">版本</th>
            <th className="px-2 py-1.5 text-left">entrypoint</th>
            <th className="px-2 py-1.5 text-left">安装于</th>
            <th className="px-2 py-1.5 text-left">状态</th>
            <th className="px-2 py-1.5 text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(p => (
            <tr key={String(p.id)} className="border-t border-stone-200/70">
              <td className="px-2 py-1.5 font-mono text-[11px]">
                {p.plugin_key}
                {p.manifest?.description && (
                  <div className="text-[10.5px] text-stone-500">
                    {p.manifest.description}
                  </div>
                )}
              </td>
              <td className="px-2 py-1.5">
                <Badge
                  variant="outline"
                  className={cn(
                    'text-[10.5px]',
                    TYPE_COLOR[p.type] ?? 'bg-stone-50 text-stone-600',
                  )}
                >
                  {TYPE_LABEL[p.type] ?? p.type}
                </Badge>
              </td>
              <td className="px-2 py-1.5 font-mono text-[10.5px] text-stone-600">
                {p.version}
              </td>
              <td className="px-2 py-1.5 font-mono text-[10.5px] text-stone-500">
                {p.manifest?.entrypoint ?? '—'}
              </td>
              <td className="px-2 py-1.5 font-mono text-[10.5px] text-stone-500">
                {formatDateTime(p.installed_at)}
              </td>
              <td className="px-2 py-1.5">
                <Badge
                  variant="outline"
                  className={cn(
                    'text-[10.5px]',
                    p.enabled
                      ? 'bg-emerald-50 text-emerald-700'
                      : 'bg-stone-50 text-stone-500',
                  )}
                >
                  {p.enabled ? '启用' : '禁用'}
                </Badge>
              </td>
              <td className="px-2 py-1.5 text-right">
                <div className="flex items-center justify-end gap-1">
                  <button
                    type="button"
                    title="编辑 config"
                    onClick={() => onConfig(p)}
                    className="rounded p-1 text-stone-400 hover:bg-primary-50 hover:text-primary-700"
                  >
                    <Settings className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    title="reload"
                    disabled={!p.enabled || busy}
                    onClick={() => onReload(p.id)}
                    className="rounded p-1 text-stone-400 hover:bg-stone-100 hover:text-stone-700 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    title={p.enabled ? '禁用' : '启用'}
                    disabled={busy}
                    onClick={() => onToggle(p.id, !p.enabled)}
                    className={cn(
                      'rounded px-2 py-1 text-[10.5px] font-medium',
                      p.enabled
                        ? 'bg-stone-50 text-stone-600 hover:bg-stone-200'
                        : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100',
                    )}
                  >
                    {p.enabled ? 'OFF' : 'ON'}
                  </button>
                  {onUninstall ? (
                    <button
                      type="button"
                      title="卸载"
                      onClick={() => onUninstall(p.id, p.plugin_key)}
                      className="rounded p-1 text-stone-400 hover:bg-rose-50 hover:text-rose-600"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  ) : (
                    <span
                      className="rounded p-1 text-stone-300"
                      title="builtin 不可卸载"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </span>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    )}
  </section>
);

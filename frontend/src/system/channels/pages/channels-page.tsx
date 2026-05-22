/** Channels 管理页 —— 列出 / 创建 / 编辑 / 状态切换 / 软删
 *
 * 一个 channel = 一个 provider 的一条上游 key + 调度元数据；
 * 是 P17.A1.2 abilities 矩阵 + P17.A2 failover 的底层资源。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Plus, Plug, Trash2 } from 'lucide-react';
import { useState } from 'react';

import { ConfirmDialog } from '@/core/components/common/confirm-dialog';
import { EmptyState } from '@/core/components/common/empty-state';
import {
  DataTable,
  type DataTableColumn,
  SectionCard,
  TableToolbar,
} from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { Switch } from '@/core/components/ui/switch';
import { formatRelative } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { ChannelFormModal } from '@/system/channels/components/channel-form-modal';
import { channelApi } from '@/system/channels/services/channel';
import type { ChannelItem, ChannelStatus } from '@/system/channels/types/channel';
import { providerApi } from '@/system/providers/services/provider';

const STATUS_LABEL: Record<ChannelStatus, { label: string; variant: 'success' | 'warning' | 'danger' }> = {
  enabled: { label: '启用', variant: 'success' },
  auto_disabled: { label: '自动停用', variant: 'warning' },
  manual_disabled: { label: '手动停用', variant: 'danger' },
};

export const ChannelsPage = () => {
  const qc = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<ChannelItem | null>(null);
  const [delTarget, setDelTarget] = useState<ChannelItem | null>(null);

  const listQ = useQuery({
    queryKey: ['channels'],
    queryFn: () => channelApi.list(),
  });
  const providersQ = useQuery({
    queryKey: ['providers'],
    queryFn: () => providerApi.list(),
  });

  const closeForm = () => {
    setFormOpen(false);
    setEditTarget(null);
  };

  const createMut = useMutation({
    mutationFn: channelApi.create,
    onSuccess: () => {
      toast.success('Channel 已创建');
      qc.invalidateQueries({ queryKey: ['channels'] });
      closeForm();
    },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, req }: { id: EntityId; req: Parameters<typeof channelApi.update>[1] }) =>
      channelApi.update(id, req),
    onSuccess: () => {
      toast.success('已保存');
      qc.invalidateQueries({ queryKey: ['channels'] });
      closeForm();
    },
  });

  const delMut = useMutation({
    mutationFn: (id: EntityId) => channelApi.delete(id),
    onSuccess: () => {
      toast.success('已删除');
      qc.invalidateQueries({ queryKey: ['channels'] });
      setDelTarget(null);
    },
  });

  /** 启用 / 禁用快速切换（auto_disabled 也走这个，统一恢复为 enabled） */
  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: EntityId; enabled: boolean }) =>
      channelApi.update(id, { status: enabled ? 'enabled' : 'manual_disabled' }),
    onMutate: async ({ id, enabled }) => {
      await qc.cancelQueries({ queryKey: ['channels'] });
      const prev = qc.getQueryData<ChannelItem[]>(['channels']);
      qc.setQueryData<ChannelItem[]>(['channels'], old =>
        old?.map(c =>
          c.id === id ? { ...c, status: enabled ? 'enabled' : 'manual_disabled' } : c,
        ),
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(['channels'], ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['channels'] }),
  });

  const columns: DataTableColumn<ChannelItem>[] = [
    {
      key: 'name',
      header: '名称',
      render: c => (
        <div className="flex flex-col gap-0.5">
          <span className="text-[12.5px] font-medium text-stone-900">{c.name}</span>
          <span className="font-mono text-[10.5px] text-stone-400">id={c.id}</span>
        </div>
      ),
    },
    {
      key: 'provider',
      header: 'Provider',
      width: 140,
      render: c => (
        <Badge variant="primary">{c.provider_code || `#${c.provider_id}`}</Badge>
      ),
    },
    {
      key: 'status',
      header: '状态',
      width: 110,
      render: c => {
        const conf = STATUS_LABEL[c.status];
        return <Badge variant={conf.variant}>{conf.label}</Badge>;
      },
    },
    {
      key: 'priority',
      header: 'P / W',
      width: 90,
      align: 'right',
      render: c => (
        <span className="tnum font-mono text-[11.5px] text-stone-600">
          {c.priority} / {c.weight}
        </span>
      ),
    },
    {
      key: 'health',
      header: '健康',
      width: 200,
      render: c => (
        <div className="flex flex-col gap-0.5 text-[11px] text-stone-500">
          <div className="flex items-center gap-2">
            <span>失败 {c.fail_count}</span>
            {c.response_time_ms !== null ? (
              <span className="tnum">· {c.response_time_ms}ms</span>
            ) : null}
          </div>
          <div className="text-[10.5px] text-stone-400">
            {c.last_success_at
              ? `上次成功 ${formatRelative(c.last_success_at)}`
              : '从未调用'}
          </div>
        </div>
      ),
    },
    {
      key: 'has_key',
      header: 'API Key',
      width: 80,
      render: c =>
        c.has_api_key ? (
          <Badge variant="success">已配</Badge>
        ) : (
          <Badge variant="outline">未配</Badge>
        ),
    },
    {
      key: 'enabled',
      header: '启用',
      width: 70,
      render: c => (
        <Switch
          checked={c.status === 'enabled'}
          onCheckedChange={v => toggleMut.mutate({ id: c.id, enabled: v })}
        />
      ),
    },
    {
      key: 'actions',
      header: '操作',
      align: 'right',
      width: 120,
      render: c => (
        <div className="inline-flex items-center gap-0.5">
          <button
            type="button"
            title="编辑"
            className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-[11.5px] text-stone-600 hover:bg-stone-200 hover:text-stone-900"
            onClick={() => {
              setEditTarget(c);
              setFormOpen(true);
            }}
          >
            <Pencil className="h-3.5 w-3.5" /> 编辑
          </button>
          <button
            type="button"
            title="删除"
            className="rounded p-1 text-stone-600 hover:bg-red-100 hover:text-red-600"
            onClick={() => setDelTarget(c)}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <SectionCard>
        <TableToolbar
          title="Channels（凭证 & 路由）"
          extra={
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                setEditTarget(null);
                setFormOpen(true);
              }}
            >
              <Plus className="h-3.5 w-3.5" /> 新建 Channel
            </Button>
          }
        />
        <DataTable
          columns={columns}
          rows={listQ.data || []}
          rowKey="id"
          loading={listQ.isLoading}
          emptyText={
            <EmptyState
              icon={<Plug strokeWidth={1.5} />}
              title="还没有 Channel"
              description="一个 channel = 一个 provider 的一条上游 key；同一 model 路由到多 channel 实现 failover + 负载均衡。"
              action={
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => {
                    setEditTarget(null);
                    setFormOpen(true);
                  }}
                >
                  <Plus className="h-3.5 w-3.5" /> 新建 Channel
                </Button>
              }
            />
          }
        />
      </SectionCard>

      <ChannelFormModal
        open={formOpen}
        initial={editTarget}
        providers={providersQ.data || []}
        loading={createMut.isPending || updateMut.isPending}
        onClose={closeForm}
        onSubmitCreate={req => createMut.mutate(req)}
        onSubmitUpdate={(id, req) => updateMut.mutate({ id, req })}
      />

      <ConfirmDialog
        open={!!delTarget}
        title="删除 Channel"
        description={
          delTarget
            ? `删除 ${delTarget.name}（${delTarget.provider_code || ''}）后，所有引用该 channel 的 ability 路由将失败。`
            : ''
        }
        variant="danger"
        confirmText="删除"
        onConfirm={() => delTarget && delMut.mutate(delTarget.id)}
        onCancel={() => setDelTarget(null)}
      />
    </div>
  );
};

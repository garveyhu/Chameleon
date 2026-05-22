/** Abilities 矩阵管理页 —— (group × model_code × channel) 路由规则配置
 *
 * 矩阵语义见后端 chameleon-core/routing/router.py。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Network, Plus, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';

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
import { Input } from '@/core/components/ui/input';
import { Switch } from '@/core/components/ui/switch';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { AbilityFormModal } from '@/system/abilities/components/ability-form-modal';
import { abilityApi } from '@/system/abilities/services/ability';
import type {
  AbilityItem,
  UpdateAbilityRequest,
} from '@/system/abilities/types/ability';
import { channelApi } from '@/system/channels/services/channel';

export const AbilitiesPage = () => {
  const qc = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [delTarget, setDelTarget] = useState<AbilityItem | null>(null);

  const listQ = useQuery({
    queryKey: ['abilities'],
    queryFn: () => abilityApi.list(),
  });
  const channelsQ = useQuery({
    queryKey: ['channels'],
    queryFn: () => channelApi.list(),
  });

  const createMut = useMutation({
    mutationFn: abilityApi.create,
    onSuccess: () => {
      toast.success('Ability 已创建');
      qc.invalidateQueries({ queryKey: ['abilities'] });
      setFormOpen(false);
    },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, req }: { id: EntityId; req: UpdateAbilityRequest }) =>
      abilityApi.update(id, req),
    onMutate: async ({ id, req }) => {
      await qc.cancelQueries({ queryKey: ['abilities'] });
      const prev = qc.getQueryData<AbilityItem[]>(['abilities']);
      qc.setQueryData<AbilityItem[]>(['abilities'], old =>
        old?.map(a => (a.id === id ? { ...a, ...req } : a)),
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(['abilities'], ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['abilities'] }),
  });

  const delMut = useMutation({
    mutationFn: (id: EntityId) => abilityApi.delete(id),
    onSuccess: () => {
      toast.success('已删除');
      qc.invalidateQueries({ queryKey: ['abilities'] });
      setDelTarget(null);
    },
  });

  // 按 model_code 分组展示矩阵感
  const grouped = useMemo(() => {
    const items = listQ.data ?? [];
    const m = new Map<string, AbilityItem[]>();
    for (const it of items) {
      const arr = m.get(it.model_code) ?? [];
      arr.push(it);
      m.set(it.model_code, arr);
    }
    return Array.from(m.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [listQ.data]);

  const columns: DataTableColumn<AbilityItem>[] = [
    {
      key: 'model_code',
      header: 'Model Code',
      render: a => <span className="font-mono text-[12.5px] font-medium text-stone-900">{a.model_code}</span>,
    },
    {
      key: 'channel',
      header: 'Channel',
      width: 200,
      render: a => (
        <div className="flex flex-col gap-0.5">
          <Badge variant="primary">{a.provider_code || '?'}</Badge>
          <span className="text-[11px] text-stone-500">{a.channel_name || '?'}</span>
        </div>
      ),
    },
    {
      key: 'group',
      header: 'Group',
      width: 100,
      render: a =>
        a.group_id === null ? (
          <Badge variant="outline">全局</Badge>
        ) : (
          <span className="font-mono text-[11.5px] text-stone-600">{a.group_id}</span>
        ),
    },
    {
      key: 'priority',
      header: 'Priority',
      width: 100,
      align: 'right',
      render: a => (
        <Input
          type="number"
          value={a.priority}
          min={0}
          step={1}
          className="w-16 text-right tnum"
          onChange={e => {
            const v = Number(e.target.value);
            if (Number.isFinite(v) && v >= 0 && v !== a.priority) {
              updateMut.mutate({ id: a.id, req: { priority: v } });
            }
          }}
        />
      ),
    },
    {
      key: 'weight',
      header: 'Weight',
      width: 100,
      align: 'right',
      render: a => (
        <Input
          type="number"
          value={a.weight}
          min={0}
          step={1}
          className="w-16 text-right tnum"
          onChange={e => {
            const v = Number(e.target.value);
            if (Number.isFinite(v) && v >= 0 && v !== a.weight) {
              updateMut.mutate({ id: a.id, req: { weight: v } });
            }
          }}
        />
      ),
    },
    {
      key: 'enabled',
      header: '启用',
      width: 70,
      render: a => (
        <Switch
          checked={a.enabled}
          onCheckedChange={v => updateMut.mutate({ id: a.id, req: { enabled: v } })}
        />
      ),
    },
    {
      key: 'actions',
      header: '操作',
      align: 'right',
      width: 80,
      render: a => (
        <button
          type="button"
          title="删除"
          className="rounded p-1 text-stone-600 hover:bg-red-100 hover:text-red-600"
          onClick={() => setDelTarget(a)}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <SectionCard>
        <TableToolbar
          title="Abilities（矩阵路由规则）"
          extra={
            <Button variant="primary" size="sm" onClick={() => setFormOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> 新建 Ability
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
              icon={<Network strokeWidth={1.5} />}
              title="还没有 Ability"
              description="一条 ability = (group × model_code × channel)。同 model_code 可有多 channel；运行时按 priority+weight 加权随机选。"
              action={
                <Button variant="primary" size="sm" onClick={() => setFormOpen(true)}>
                  <Plus className="h-3.5 w-3.5" /> 新建 Ability
                </Button>
              }
            />
          }
        />
      </SectionCard>

      {/* 按 model_code 分组的概览（仅当 >1 model_code 时显示，给 admin 一眼看矩阵） */}
      {grouped.length > 1 ? (
        <SectionCard>
          <div className="border-b border-stone-200/70 px-4 py-2 text-[12.5px] font-semibold text-stone-700">
            按 Model Code 路由概览
          </div>
          <div className="space-y-3 p-4">
            {grouped.map(([mc, items]) => (
              <div key={mc}>
                <div className="mb-1 font-mono text-[12px] font-medium text-stone-800">{mc}</div>
                <div className="flex flex-wrap gap-1.5">
                  {items
                    .sort((a, b) => b.priority - a.priority || b.weight - a.weight)
                    .map(a => (
                      <Badge
                        key={a.id}
                        variant={a.enabled ? 'success' : 'outline'}
                        className="font-mono text-[11px]"
                      >
                        {a.provider_code || '?'} / {a.channel_name || '?'} · P{a.priority} W{a.weight}
                      </Badge>
                    ))}
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      ) : null}

      <AbilityFormModal
        open={formOpen}
        channels={channelsQ.data || []}
        loading={createMut.isPending}
        onClose={() => setFormOpen(false)}
        onSubmit={req => createMut.mutate(req)}
      />

      <ConfirmDialog
        open={!!delTarget}
        title="删除 Ability"
        description={
          delTarget
            ? `删除后 model_code "${delTarget.model_code}" 走该 channel 的路由将失效。`
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

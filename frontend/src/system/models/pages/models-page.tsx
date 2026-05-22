/** models 管理页 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Cpu, Plus, Trash2, Zap } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from '@/core/lib/toast';

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
import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { modelApi } from '@/system/models/services/model';
import type { ModelItem } from '@/system/models/types/model';
import { providerApi } from '@/system/providers/services/provider';

export const ModelsPage = () => {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [delModel, setDelModel] = useState<ModelItem | null>(null);

  const listQ = useQuery({ queryKey: ['models'], queryFn: () => modelApi.list() });
  const providersQ = useQuery({ queryKey: ['providers'], queryFn: providerApi.list });

  const createMut = useMutation({
    mutationFn: modelApi.create,
    onSuccess: () => {
      toast.success('模型已创建');
      qc.invalidateQueries({ queryKey: ['models'] });
      setCreateOpen(false);
    },
  });
  const delMut = useMutation({
    mutationFn: (id: import('@/core/types/api').EntityId) => modelApi.delete(id),
    onSuccess: () => {
      toast.success('已删除');
      qc.invalidateQueries({ queryKey: ['models'] });
      setDelModel(null);
    },
  });

  const testMut = useMutation({
    mutationFn: (id: import('@/core/types/api').EntityId) => modelApi.test(id),
    onSuccess: data =>
      data.ok ? toast.success(data.detail) : toast.error(data.detail),
  });

  const toggleMut = useMutation({
    mutationFn: (args: { id: import('@/core/types/api').EntityId; enabled: boolean }) =>
      modelApi.update(args.id, { enabled: args.enabled }),
    onMutate: async args => {
      await qc.cancelQueries({ queryKey: ['models'] });
      const prev = qc.getQueryData<ModelItem[]>(['models']);
      qc.setQueryData<ModelItem[]>(['models'], old =>
        old?.map(m => (m.id === args.id ? { ...m, enabled: args.enabled } : m)),
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(['models'], ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['models'] }),
  });

  const columns: DataTableColumn<ModelItem>[] = [
    { key: 'code', header: t('table.code'), render: m => <span className="font-mono text-[12px] font-medium text-stone-900">{m.code}</span> },
    {
      key: 'provider_code',
      header: t('table.provider'),
      width: 120,
      render: m => <Badge variant="primary">{m.provider_code || '?'}</Badge>,
    },
    { key: 'kind', header: t('common.type'), width: 100, render: m => <Badge>{m.kind}</Badge> },
    { key: 'dim', header: t('table.dim'), width: 80, align: 'right', render: m => <span className="tnum font-mono text-[11.5px]">{m.dim ?? '—'}</span> },
    {
      key: 'defaults',
      header: t('table.defaults'),
      render: m => (
        <span className="font-mono text-[11.5px] text-stone-500">
          {m.defaults ? JSON.stringify(m.defaults).slice(0, 60) : '—'}
        </span>
      ),
    },
    {
      key: 'enabled',
      header: t('common.enabled'),
      width: 70,
      render: m => (
        <Switch
          checked={m.enabled}
          onCheckedChange={c => toggleMut.mutate({ id: m.id, enabled: c })}
        />
      ),
    },
    {
      key: 'actions',
      header: t('common.actions'),
      align: 'right',
      width: 110,
      render: m => (
        <div className="inline-flex items-center gap-0.5">
          <button
            type="button"
            title={t('common.test')}
            className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-[11.5px] text-stone-600 hover:bg-stone-200 hover:text-stone-900 disabled:opacity-50"
            onClick={() => testMut.mutate(m.id)}
            disabled={testMut.isPending}
          >
            <Zap className="h-3.5 w-3.5" /> {t('common.test')}
          </button>
          <button
            type="button"
            title="删除"
            className="rounded p-1 text-stone-600 hover:bg-red-100 hover:text-red-600"
            onClick={() => setDelModel(m)}
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
          title={t('page.models_title')}
          extra={
            <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> {t('common.create')}
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
              icon={<Cpu strokeWidth={1.5} />}
              title={t('empty.models')}
              action={
                <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
                  <Plus className="h-3.5 w-3.5" /> {t('common.create')}
                </Button>
              }
            />
          }
        />
      </SectionCard>
      <CreateModelModal
        open={createOpen}
        providers={providersQ.data || []}
        onClose={() => setCreateOpen(false)}
        onSubmit={createMut.mutate}
        loading={createMut.isPending}
      />
      <ConfirmDialog
        open={!!delModel}
        title="删除模型"
        description={`确定删除 ${delModel?.code}？相关 agent 调用将失败。`}
        variant="danger"
        confirmText="删除"
        onConfirm={() => delModel && delMut.mutate(delModel.id)}
        onCancel={() => setDelModel(null)}
      />
    </div>
  );
};

const CreateModelModal = ({
  open,
  providers,
  onClose,
  onSubmit,
  loading,
}: {
  open: boolean;
  providers: { id: import('@/core/types/api').EntityId; code: string }[];
  onClose: () => void;
  onSubmit: (req: { provider_id: import('@/core/types/api').EntityId; code: string; kind: 'chat' | 'embedding'; dim?: number }) => void;
  loading: boolean;
}) => {
  const [providerId, setProviderId] = useState<string>('');
  const [code, setCode] = useState('');
  const [kind, setKind] = useState<'chat' | 'embedding'>('chat');
  const [dim, setDim] = useState<string>('');

  return (
    <Modal
      open={open}
      onOpenChange={o => {
        if (!o) {
          setProviderId('');
          setCode('');
          setKind('chat');
          setDim('');
          onClose();
        }
      }}
    >
      <ModalContent size="md">
        <ModalHeader>
          <ModalTitle>新建模型</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div className="space-y-1.5">
            <Label>Provider</Label>
            <Select value={providerId} onValueChange={setProviderId}>
              <SelectTrigger>
                <SelectValue placeholder="选择 provider" />
              </SelectTrigger>
              <SelectContent>
                {providers.map(p => (
                  <SelectItem key={p.id} value={String(p.id)}>
                    {p.code}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>模型 code</Label>
            <Input value={code} onChange={e => setCode(e.target.value)} placeholder="qwen-plus" />
          </div>
          <div className="space-y-1.5">
            <Label>kind</Label>
            <Select value={kind} onValueChange={v => setKind(v as 'chat' | 'embedding')}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="chat">chat（LLM）</SelectItem>
                <SelectItem value="embedding">embedding</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {kind === 'embedding' && (
            <div className="space-y-1.5">
              <Label>维度</Label>
              <Input
                type="number"
                value={dim}
                onChange={e => setDim(e.target.value)}
                placeholder="1536"
              />
            </div>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button
            disabled={loading || !providerId || !code}
            onClick={() =>
              onSubmit({
                provider_id: Number(providerId),
                code,
                kind,
                dim: dim ? Number(dim) : undefined,
              })
            }
          >
            {loading ? '创建中...' : '创建'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

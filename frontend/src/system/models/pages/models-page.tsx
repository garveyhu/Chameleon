/** models 管理页 —— 按用途分组的现代卡片网格 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowDownUp, Boxes, Cpu, MessageSquare, Plus } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ConfirmDialog } from '@/core/components/common/confirm-dialog';
import { EmptyState } from '@/core/components/common/empty-state';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { ModelCard } from '@/system/models/components/model-card';
import { ModelConfigSheet } from '@/system/models/components/model-config-sheet';
import { TestModelModal } from '@/system/models/components/test-model-modal';
import { modelApi } from '@/system/models/services/model';
import type { ModelItem } from '@/system/models/types/model';
import { providerApi } from '@/system/providers/services/provider';

const GROUPS = [
  { kind: 'chat', label: '对话模型', icon: MessageSquare },
  { kind: 'embedding', label: '向量模型', icon: Boxes },
  { kind: 'rerank', label: '重排模型', icon: ArrowDownUp },
] as const;

export const ModelsPage = () => {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [delModel, setDelModel] = useState<ModelItem | null>(null);
  const [testModel, setTestModel] = useState<ModelItem | null>(null);
  const [configModel, setConfigModel] = useState<ModelItem | null>(null);

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
    mutationFn: (id: EntityId) => modelApi.delete(id),
    onSuccess: () => {
      toast.success('已删除');
      qc.invalidateQueries({ queryKey: ['models'] });
      setDelModel(null);
    },
  });
  const toggleMut = useMutation({
    mutationFn: (args: { id: EntityId; enabled: boolean }) =>
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

  const models = listQ.data ?? [];
  const groups = GROUPS.map(g => ({
    ...g,
    items: models.filter(m => m.kind === g.kind),
  })).filter(g => g.items.length > 0);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-[16px] font-semibold text-stone-900">
            {t('page.models_title')}
          </h1>
          <p className="mt-0.5 text-[12px] text-stone-500">
            逻辑模型目录 —— 能力、上游映射与运行参数在此管理
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="h-3.5 w-3.5" /> {t('common.create')}
        </Button>
      </header>

      {listQ.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-[132px] animate-pulse rounded-xl border border-stone-200 bg-stone-50"
            />
          ))}
        </div>
      ) : models.length === 0 ? (
        <EmptyState
          icon={<Cpu strokeWidth={1.5} />}
          title={t('empty.models')}
          action={
            <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> {t('common.create')}
            </Button>
          }
        />
      ) : (
        groups.map(g => (
          <section key={g.kind} className="space-y-3">
            <div className="flex items-center gap-2">
              <g.icon className="h-4 w-4 text-stone-400" strokeWidth={1.75} />
              <h2 className="text-[13px] font-medium text-stone-700">{g.label}</h2>
              <span className="rounded-full bg-stone-100 px-1.5 py-0.5 text-[10.5px] font-medium text-stone-500">
                {g.items.length}
              </span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {g.items.map(m => (
                <ModelCard
                  key={String(m.id)}
                  model={m}
                  onConfig={() => setConfigModel(m)}
                  onTest={() => setTestModel(m)}
                  onDelete={() => setDelModel(m)}
                  onToggle={c => toggleMut.mutate({ id: m.id, enabled: c })}
                />
              ))}
            </div>
          </section>
        ))
      )}

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
      <TestModelModal model={testModel} onClose={() => setTestModel(null)} />
      <ModelConfigSheet model={configModel} onClose={() => setConfigModel(null)} />
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
  providers: { id: EntityId; code: string }[];
  onClose: () => void;
  onSubmit: (req: {
    provider_id: EntityId;
    code: string;
    kind: 'chat' | 'embedding';
    dim?: number;
  }) => void;
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
                provider_id: providerId,
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

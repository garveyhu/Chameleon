/** models 管理页 —— 按用途分组的现代卡片网格 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowDownUp,
  Boxes,
  Cpu,
  Image as ImageIcon,
  MessageSquare,
  Plus,
  Power,
} from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ConfirmDialog } from '@/core/components/common/confirm-dialog';
import { EmptyState } from '@/core/components/common/empty-state';
import { MiniStat } from '@/core/components/common/mini-stat';
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
import { imagegenApi } from '@/system/models/services/imagegen';
import { modelApi } from '@/system/models/services/model';
import type { ModelItem } from '@/system/models/types/model';
import { providerApi } from '@/system/providers/services/provider';
import { settingsApi } from '@/system/settings/services/settings';

const GROUPS = [
  { kind: 'chat', label: '对话模型', icon: MessageSquare },
  { kind: 'embedding', label: '向量模型', icon: Boxes },
  { kind: 'rerank', label: '重排模型', icon: ArrowDownUp },
  { kind: 'image', label: '生图模型', icon: ImageIcon },
] as const;

// 卡片「设为默认」按 kind 写对应 model_defaults case
const KIND_TO_CASE: Record<string, string> = {
  chat: 'llm',
  embedding: 'embedding',
  rerank: 'rerank',
};

export const ModelsPage = () => {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [delModel, setDelModel] = useState<ModelItem | null>(null);
  const [testModel, setTestModel] = useState<ModelItem | null>(null);
  const [configModel, setConfigModel] = useState<ModelItem | null>(null);

  const listQ = useQuery({ queryKey: ['models'], queryFn: () => modelApi.list() });
  const providersQ = useQuery({ queryKey: ['providers'], queryFn: providerApi.list });
  const defaultsQ = useQuery({
    queryKey: ['model-defaults'],
    queryFn: settingsApi.listModelDefaults,
  });

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
  const setDefaultMut = useMutation({
    mutationFn: (m: ModelItem) =>
      settingsApi.updateModelDefault(KIND_TO_CASE[m.kind], m.id),
    onSuccess: () => {
      toast.success('已设为默认');
      qc.invalidateQueries({ queryKey: ['model-defaults'] });
      qc.invalidateQueries({ queryKey: ['models'] });
    },
  });

  const models = listQ.data ?? [];
  const defaultIds = new Set(
    (defaultsQ.data ?? [])
      .filter(d => d.model_id != null)
      .map(d => String(d.model_id)),
  );
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

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MiniStat label="模型总数" value={models.length} icon={Cpu} tone="primary" />
        <MiniStat
          label="对话模型"
          value={models.filter(m => m.kind === 'chat').length}
          icon={MessageSquare}
          tone="primary"
        />
        <MiniStat
          label="向量模型"
          value={models.filter(m => m.kind === 'embedding').length}
          icon={Boxes}
          tone="violet"
        />
        <MiniStat
          label="已启用"
          value={models.filter(m => m.enabled).length}
          icon={Power}
          tone="success"
        />
      </div>

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
                  isDefault={defaultIds.has(String(m.id))}
                  onConfig={() => setConfigModel(m)}
                  onTest={() => setTestModel(m)}
                  onDelete={() => setDelModel(m)}
                  onToggle={c => toggleMut.mutate({ id: m.id, enabled: c })}
                  onSetDefault={() => setDefaultMut.mutate(m)}
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
      <ModelConfigSheet
        model={configModel}
        providers={providersQ.data || []}
        onClose={() => setConfigModel(null)}
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
  providers: { id: EntityId; code: string }[];
  onClose: () => void;
  onSubmit: (req: {
    provider_id: EntityId;
    code: string;
    kind: 'chat' | 'embedding' | 'rerank' | 'image';
    dim?: number;
    defaults?: Record<string, unknown>;
  }) => void;
  loading: boolean;
}) => {
  const [providerId, setProviderId] = useState<string>('');
  const [code, setCode] = useState('');
  const [kind, setKind] = useState<'chat' | 'embedding' | 'rerank' | 'image'>('chat');
  const [dim, setDim] = useState<string>('');
  const [imageDriver, setImageDriver] = useState<'comfyui' | 'dashscope'>('comfyui');
  const [workflow, setWorkflow] = useState('');
  const [upstreamModel, setUpstreamModel] = useState('');
  const [imageSize, setImageSize] = useState('1280*1280');
  const workflowsQ = useQuery({
    queryKey: ['imagegen-workflows'],
    queryFn: imagegenApi.listWorkflows,
    enabled: open && kind === 'image' && imageDriver === 'comfyui',
  });

  return (
    <Modal
      open={open}
      onOpenChange={o => {
        if (!o) {
          setProviderId('');
          setCode('');
          setKind('chat');
          setDim('');
          setImageDriver('comfyui');
          setWorkflow('');
          setUpstreamModel('');
          setImageSize('1280*1280');
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
            <Label>供应商</Label>
            <Select value={providerId} onValueChange={setProviderId}>
              <SelectTrigger>
                <SelectValue placeholder="选择供应商" />
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
            <Label>模型标识 (code)</Label>
            <Input value={code} onChange={e => setCode(e.target.value)} placeholder="qwen-plus" />
          </div>
          <div className="space-y-1.5">
            <Label>类型</Label>
            <Select
              value={kind}
              onValueChange={v => setKind(v as 'chat' | 'embedding' | 'rerank' | 'image')}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="chat">对话 (chat)</SelectItem>
                <SelectItem value="embedding">向量 (embedding)</SelectItem>
                <SelectItem value="rerank">重排 (rerank)</SelectItem>
                <SelectItem value="image">生图 (image)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {kind === 'embedding' && (
            <div className="space-y-1.5">
              <Label>向量维度</Label>
              <Input
                type="number"
                value={dim}
                onChange={e => setDim(e.target.value)}
                placeholder="1536"
              />
            </div>
          )}
          {kind === 'image' && (
            <>
              <div className="space-y-1.5">
                <Label>生成后端</Label>
                <Select
                  value={imageDriver}
                  onValueChange={v => setImageDriver(v as 'comfyui' | 'dashscope')}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="comfyui">本地 ComfyUI（工作流）</SelectItem>
                    <SelectItem value="dashscope">DashScope 远程（千问 / 万相）</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {imageDriver === 'comfyui' ? (
                <div className="space-y-1.5">
                  <Label>工作流</Label>
                  <Select value={workflow} onValueChange={setWorkflow}>
                    <SelectTrigger>
                      <SelectValue placeholder="选择生图工作流" />
                    </SelectTrigger>
                    <SelectContent>
                      {(workflowsQ.data ?? []).map(w => (
                        <SelectItem key={w.id} value={w.id}>
                          {w.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-[11px] text-stone-400">
                    供应商需选 ComfyUI（生图）类型；模型标识可填如 z-image-turbo。
                  </p>
                </div>
              ) : (
                <>
                  <div className="space-y-1.5">
                    <Label>上游模型 (DashScope model)</Label>
                    <Input
                      value={upstreamModel}
                      onChange={e => setUpstreamModel(e.target.value)}
                      placeholder="qwen-image"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label>默认尺寸 (size)</Label>
                    <Input
                      value={imageSize}
                      onChange={e => setImageSize(e.target.value)}
                      placeholder="1280*1280"
                    />
                  </div>
                  <p className="text-[11px] text-stone-400">
                    供应商选千问（DashScope）；复用其 API Key 直连百炼异步出图。上游模型名以百炼控制台为准。
                  </p>
                </>
              )}
            </>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button
            disabled={
              loading ||
              !providerId ||
              !code ||
              (kind === 'image' &&
                (imageDriver === 'comfyui' ? !workflow : !upstreamModel.trim()))
            }
            onClick={() =>
              onSubmit({
                provider_id: providerId,
                code,
                kind,
                dim: kind === 'embedding' && dim ? Number(dim) : undefined,
                defaults:
                  kind === 'image'
                    ? imageDriver === 'comfyui'
                      ? { workflow }
                      : {
                          driver: 'dashscope',
                          model: upstreamModel.trim(),
                          size: imageSize.trim() || '1280*1280',
                        }
                    : undefined,
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

/** providers 管理页 —— 现代供应商卡片（网关高亮 + 模型数） */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Boxes, Cloud, Network, Plus, ShieldCheck } from 'lucide-react';
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
import { modelApi } from '@/system/models/services/model';
import { ProviderCard } from '@/system/providers/components/provider-card';
import { ProviderConfigSheet } from '@/system/providers/components/provider-config-sheet';
import { providerApi } from '@/system/providers/services/provider';
import type { ProviderItem } from '@/system/providers/types/provider';

export const ProvidersPage = () => {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [delProv, setDelProv] = useState<ProviderItem | null>(null);
  const [editProv, setEditProv] = useState<ProviderItem | null>(null);

  const listQ = useQuery({ queryKey: ['providers'], queryFn: providerApi.list });
  const modelsQ = useQuery({ queryKey: ['models'], queryFn: () => modelApi.list() });

  const createMut = useMutation({
    mutationFn: providerApi.create,
    onSuccess: () => {
      toast.success('Provider 已创建');
      qc.invalidateQueries({ queryKey: ['providers'] });
      setCreateOpen(false);
    },
  });

  const delMut = useMutation({
    mutationFn: (id: EntityId) => providerApi.delete(id),
    onSuccess: () => {
      toast.success('已删除');
      qc.invalidateQueries({ queryKey: ['providers'] });
      setDelProv(null);
    },
  });

  const toggleMut = useMutation({
    mutationFn: (args: { id: EntityId; enabled: boolean }) =>
      providerApi.update(args.id, { enabled: args.enabled }),
    onMutate: async args => {
      await qc.cancelQueries({ queryKey: ['providers'] });
      const prev = qc.getQueryData<ProviderItem[]>(['providers']);
      qc.setQueryData<ProviderItem[]>(['providers'], old =>
        old?.map(p => (p.id === args.id ? { ...p, enabled: args.enabled } : p)),
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(['providers'], ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['providers'] }),
  });

  const providers = listQ.data || [];
  const models = modelsQ.data || [];
  const modelCount = (id: EntityId) =>
    models.filter(m => String(m.provider_id) === String(id)).length;

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-[16px] font-semibold text-stone-900">
            {t('page.providers_title')}
          </h1>
          <p className="mt-0.5 text-[12px] text-stone-500">
            模型 / 应用上游接入方 —— 凭证与基础地址在此管理
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="h-3.5 w-3.5" /> {t('common.create')}
        </Button>
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MiniStat label="供应商" value={providers.length} icon={Cloud} tone="primary" />
        <MiniStat
          label="已配凭证"
          value={providers.filter(p => p.has_api_key).length}
          icon={ShieldCheck}
          tone="success"
        />
        <MiniStat label="模型总数" value={models.length} icon={Boxes} tone="violet" />
        <MiniStat
          label="网关"
          value={providers.filter(p => p.kind === 'gateway').length}
          icon={Network}
          tone="sky"
        />
      </div>

      {listQ.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="h-[176px] animate-pulse rounded-xl border border-stone-200 bg-stone-50"
            />
          ))}
        </div>
      ) : providers.length === 0 ? (
        <EmptyState
          icon={<Cloud strokeWidth={1.5} />}
          title={t('empty.providers')}
          action={
            <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> {t('common.create')}
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {providers.map(p => (
            <ProviderCard
              key={String(p.id)}
              provider={p}
              modelCount={modelCount(p.id)}
              onConfig={() => setEditProv(p)}
              onDelete={() => setDelProv(p)}
              onToggle={c => toggleMut.mutate({ id: p.id, enabled: c })}
            />
          ))}
        </div>
      )}

      <CreateProviderModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={createMut.mutate}
        loading={createMut.isPending}
      />
      <ConfirmDialog
        open={!!delProv}
        title="删除 Provider"
        description={`删除 ${delProv?.code} 后，所有引用该 provider 的模型 / agent 都需要重新配置。`}
        variant="danger"
        confirmText="删除"
        onConfirm={() => delProv && delMut.mutate(delProv.id)}
        onCancel={() => setDelProv(null)}
      />
      <ProviderConfigSheet provider={editProv} onClose={() => setEditProv(null)} />
    </div>
  );
};

const CreateProviderModal = ({
  open,
  onClose,
  onSubmit,
  loading,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (req: {
    code: string;
    kind: ProviderItem['kind'];
    name: string;
    base_url?: string;
    api_key?: string;
  }) => void;
  loading: boolean;
}) => {
  const [code, setCode] = useState('');
  const [kind, setKind] = useState<ProviderItem['kind']>('llm');
  const [name, setName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');

  return (
    <Modal
      open={open}
      onOpenChange={o => {
        if (!o) {
          setCode('');
          setName('');
          setBaseUrl('');
          setApiKey('');
          setKind('llm');
          onClose();
        }
      }}
    >
      <ModalContent size="lg">
        <ModalHeader>
          <ModalTitle>新建 Provider</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div className="space-y-1.5">
            <Label>code（唯一标识）</Label>
            <Input value={code} onChange={e => setCode(e.target.value)} placeholder="qwen" />
          </div>
          <div className="space-y-1.5">
            <Label>kind</Label>
            <Select value={kind} onValueChange={v => setKind(v as ProviderItem['kind'])}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="llm">llm</SelectItem>
                <SelectItem value="embedding">embedding</SelectItem>
                <SelectItem value="gateway">gateway（new-api 统一网关）</SelectItem>
                <SelectItem value="dify">dify</SelectItem>
                <SelectItem value="fastgpt">fastgpt</SelectItem>
                <SelectItem value="coze">coze</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>名称</Label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="通义千问" />
          </div>
          <div className="space-y-1.5">
            <Label>base_url</Label>
            <Input
              value={baseUrl}
              onChange={e => setBaseUrl(e.target.value)}
              placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1"
            />
          </div>
          <div className="space-y-1.5">
            <Label>API Key（写入后会 AES-256-GCM 加密）</Label>
            <Input
              type="password"
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              placeholder="sk-xxxxx"
            />
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button
            disabled={loading || !code || !name}
            onClick={() =>
              onSubmit({
                code,
                kind,
                name,
                base_url: baseUrl || undefined,
                api_key: apiKey || undefined,
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

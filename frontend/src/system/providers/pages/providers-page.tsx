/** providers 管理页 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Cloud, Pencil, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from '@/core/lib/toast';

import { ConfirmDialog } from '@/core/components/common/confirm-dialog';
import { EmptyState } from '@/core/components/common/empty-state';
import { SectionCard } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { StatusBadge } from '@/core/components/ui/status-badge';
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

  const createMut = useMutation({
    mutationFn: providerApi.create,
    onSuccess: () => {
      toast.success('Provider 已创建');
      qc.invalidateQueries({ queryKey: ['providers'] });
      setCreateOpen(false);
    },
  });

  const delMut = useMutation({
    mutationFn: (id: import('@/core/types/api').EntityId) => providerApi.delete(id),
    onSuccess: () => {
      toast.success('已删除');
      qc.invalidateQueries({ queryKey: ['providers'] });
      setDelProv(null);
    },
  });

  const toggleMut = useMutation({
    mutationFn: (args: { id: import('@/core/types/api').EntityId; enabled: boolean }) =>
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

  return (
    <div>
      <SectionCard>
        <header className="mb-4 flex items-center justify-between">
          <div>
            <h1 className="text-[15px] font-medium text-stone-900">
              {t('page.providers_title')}
            </h1>
            <p className="mt-0.5 text-[11.5px] text-stone-500">
              模型 / 应用上游接入方——凭证与基础地址在此管理
            </p>
          </div>
          <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-3.5 w-3.5" /> {t('common.create')}
          </Button>
        </header>

        {listQ.isLoading ? (
          <div className="py-12 text-center text-[12px] text-stone-400">加载中…</div>
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
              <div
                key={String(p.id)}
                className="flex flex-col rounded-xl border border-stone-200 bg-[var(--color-paper)] p-5 transition hover:border-stone-300 hover:shadow-pop"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2.5">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-sky-50 text-sky-600">
                      <Cloud className="h-4 w-4" strokeWidth={1.75} />
                    </div>
                    <div className="min-w-0">
                      <div className="truncate text-[14px] font-medium text-stone-900">
                        {p.name}
                      </div>
                      <div className="truncate font-mono text-[11px] text-stone-400">
                        {p.code}
                      </div>
                    </div>
                  </div>
                  <Badge variant="primary" className="shrink-0">
                    {p.kind}
                  </Badge>
                </div>

                <div className="mt-4 space-y-2">
                  {p.has_api_key ? (
                    <StatusBadge tone="success">凭证已配</StatusBadge>
                  ) : (
                    <StatusBadge tone="warning">凭证未配</StatusBadge>
                  )}
                  <div
                    className="truncate font-mono text-[11px] text-stone-500"
                    title={p.base_url || ''}
                  >
                    {p.base_url || '默认地址'}
                  </div>
                </div>

                <div className="mt-4 flex items-center justify-between border-t border-stone-100 pt-3">
                  <div className="flex items-center gap-2">
                    <Switch
                      checked={p.enabled}
                      onCheckedChange={c => toggleMut.mutate({ id: p.id, enabled: c })}
                    />
                    <span className="text-[11px] text-stone-400">
                      {p.enabled ? '已启用' : '已停用'}
                    </span>
                  </div>
                  <div className="flex items-center gap-0.5">
                    <button
                      type="button"
                      title="配置"
                      className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded px-2 py-1 text-[11.5px] text-stone-600 hover:bg-stone-100 hover:text-stone-900"
                      onClick={() => setEditProv(p)}
                    >
                      <Pencil className="h-3.5 w-3.5" /> 配置
                    </button>
                    <button
                      type="button"
                      title="删除"
                      className="shrink-0 rounded p-1 text-stone-500 hover:bg-red-100 hover:text-red-600"
                      onClick={() => setDelProv(p)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </SectionCard>
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

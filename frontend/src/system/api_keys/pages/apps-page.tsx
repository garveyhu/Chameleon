/** Key 管理：按作用域分组的现代卡片 + 新建 / 撤销 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bot, Copy, Globe, KeyRound, Plus, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ConfirmDialog } from '@/core/components/common/confirm-dialog';
import { EmptyState } from '@/core/components/common/empty-state';
import { MiniStat } from '@/core/components/common/mini-stat';
import { Button } from '@/core/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/core/components/ui/dialog';
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
import { Textarea } from '@/core/components/ui/textarea';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { KeyCard } from '@/system/api_keys/components/key-card';
import { SCOPE } from '@/system/api_keys/scope';
import { apiKeyApi } from '@/system/api_keys/services/app';
import type {
  ApiKeyCreated,
  ApiKeyItem,
  ApiKeyScopeType,
  CreateApiKeyRequest,
} from '@/system/api_keys/types/app';

const GROUPS: { scope: ApiKeyScopeType; label: string }[] = [
  { scope: 'app', label: '应用密钥' },
  { scope: 'kb', label: '知识库密钥' },
  { scope: 'global', label: '通用密钥' },
];

export const AppsPage = () => {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [revokeKey, setRevokeKey] = useState<ApiKeyItem | null>(null);
  const [plain, setPlain] = useState<ApiKeyCreated | null>(null);

  const listQ = useQuery({
    queryKey: ['api-keys'],
    queryFn: () => apiKeyApi.list({ page: 1, page_size: 100, include_revoked: true }),
  });

  const createMut = useMutation({
    mutationFn: apiKeyApi.create,
    onSuccess: created => {
      qc.invalidateQueries({ queryKey: ['api-keys'] });
      setCreateOpen(false);
      setPlain(created);
    },
  });

  const revokeMut = useMutation({
    mutationFn: (id: EntityId) => apiKeyApi.revoke(id),
    onSuccess: () => {
      toast.success('Key 已撤销');
      qc.invalidateQueries({ queryKey: ['api-keys'] });
      setRevokeKey(null);
    },
  });

  const keys = listQ.data?.items ?? [];
  const groups = GROUPS.map(g => ({
    ...g,
    items: keys.filter(k => k.scope_type === g.scope),
  })).filter(g => g.items.length > 0);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-[16px] font-semibold text-stone-900">
            {t('page.api_keys_title')}
          </h1>
          <p className="mt-0.5 text-[12px] text-stone-500">
            对外签发的访问密钥 —— 作用域、配额与状态在此管理
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="h-3.5 w-3.5" /> {t('common.create')}
        </Button>
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MiniStat label="密钥总数" value={keys.length} icon={KeyRound} tone="primary" />
        <MiniStat
          label="活跃"
          value={keys.filter(k => !k.revoked_at).length}
          icon={ShieldCheck}
          tone="success"
        />
        <MiniStat
          label="应用密钥"
          value={keys.filter(k => k.scope_type === 'app').length}
          icon={Bot}
          tone="violet"
        />
        <MiniStat
          label="通用密钥"
          value={keys.filter(k => k.scope_type === 'global').length}
          icon={Globe}
          tone="sky"
        />
      </div>

      {listQ.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-[180px] animate-pulse rounded-xl border border-stone-200 bg-stone-50"
            />
          ))}
        </div>
      ) : keys.length === 0 ? (
        <EmptyState
          icon={<KeyRound strokeWidth={1.5} />}
          title={t('empty.api_keys')}
          action={
            <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> {t('common.create')}
            </Button>
          }
        />
      ) : (
        groups.map(g => {
          const Icon = SCOPE[g.scope].icon;
          return (
            <section key={g.scope} className="space-y-3">
              <div className="flex items-center gap-2">
                <Icon className="h-4 w-4 text-stone-400" />
                <h2 className="text-[13px] font-medium text-stone-700">{g.label}</h2>
                <span className="rounded-full bg-stone-100 px-1.5 py-0.5 text-[10.5px] font-medium text-stone-500">
                  {g.items.length}
                </span>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {g.items.map(k => (
                  <KeyCard key={String(k.id)} apiKey={k} onRevoke={() => setRevokeKey(k)} />
                ))}
              </div>
            </section>
          );
        })
      )}

      <CreateKeyModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={createMut.mutate}
        loading={createMut.isPending}
      />

      <ConfirmDialog
        open={!!revokeKey}
        title="撤销 API Key"
        description={`撤销后用此 Key 的调用将被拒绝，且不可恢复（${revokeKey?.name}）。`}
        variant="danger"
        confirmText="撤销"
        onConfirm={() => revokeKey && revokeMut.mutate(revokeKey.id)}
        onCancel={() => setRevokeKey(null)}
      />

      <PlainKeyDialog plain={plain} onClose={() => setPlain(null)} />
    </div>
  );
};

// ── 新建 Key ────────────────────────────────────────────────

const CreateKeyModal = ({
  open,
  onClose,
  onSubmit,
  loading,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (req: CreateApiKeyRequest) => void;
  loading: boolean;
}) => {
  const [name, setName] = useState('');
  const [appId, setAppId] = useState('');
  const [scopeType, setScopeType] = useState<ApiKeyScopeType>('global');
  const [scopeRef, setScopeRef] = useState('');
  const [scopes, setScopes] = useState('');
  const [desc, setDesc] = useState('');

  const reset = () => {
    setName('');
    setAppId('');
    setScopeType('global');
    setScopeRef('');
    setScopes('');
    setDesc('');
  };

  const canSubmit = !!name && (scopeType === 'global' || !!scopeRef);

  return (
    <Modal
      open={open}
      onOpenChange={o => {
        if (!o) {
          reset();
          onClose();
        }
      }}
    >
      <ModalContent size="md">
        <ModalHeader>
          <ModalTitle>新建 API Key</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div className="space-y-1.5">
            <Label>名称</Label>
            <Input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="prod / ci / mobile-app"
            />
            <p className="text-[11px] text-stone-500">只用于识别和撤销，不是密钥本身</p>
          </div>
          <div className="space-y-1.5">
            <Label>作用域</Label>
            <Select value={scopeType} onValueChange={v => setScopeType(v as ApiKeyScopeType)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="global">通用（通吃所有服务）</SelectItem>
                <SelectItem value="app">应用（仅某智能体）</SelectItem>
                <SelectItem value="kb">知识库（仅某知识库）</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {scopeType !== 'global' ? (
            <div className="space-y-1.5">
              <Label>目标标识</Label>
              <Input
                value={scopeRef}
                onChange={e => setScopeRef(e.target.value)}
                placeholder={scopeType === 'app' ? 'agent_key' : 'kb_key'}
                className="font-mono text-[12.5px]"
              />
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label>来源标签（可选）</Label>
            <Input
              value={appId}
              onChange={e => setAppId(e.target.value)}
              placeholder="留空则用名称自动生成"
              className="font-mono text-[12.5px]"
            />
            <p className="text-[11px] text-stone-500">仅用于调用日志聚合 / 展示</p>
          </div>
          <div className="space-y-1.5">
            <Label>scopes（逗号分隔，可选）</Label>
            <Input
              value={scopes}
              onChange={e => setScopes(e.target.value)}
              placeholder="留空 = 仅业务接口；admin = 含管理接口"
            />
          </div>
          <div className="space-y-1.5">
            <Label>描述</Label>
            <Textarea value={desc} onChange={e => setDesc(e.target.value)} rows={2} />
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button
            disabled={!canSubmit || loading}
            onClick={() =>
              onSubmit({
                name,
                app_id: appId.trim() || undefined,
                scope_type: scopeType,
                scope_ref: scopeType === 'global' ? undefined : scopeRef.trim(),
                scopes: scopes
                  ? scopes
                      .split(',')
                      .map(s => s.trim())
                      .filter(Boolean)
                  : [],
                description: desc || undefined,
              })
            }
          >
            {loading ? '签发中...' : '签发并生成密钥'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

// ── 新签发明文 token ────────────────────────────────────────

const PlainKeyDialog = ({
  plain,
  onClose,
}: {
  plain: ApiKeyCreated | null;
  onClose: () => void;
}) => {
  const copy = () => {
    if (plain?.plain_key) {
      navigator.clipboard.writeText(plain.plain_key);
      toast.success('已复制');
    }
  };
  return (
    <Dialog open={!!plain} onOpenChange={o => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新 API Key 已签发</DialogTitle>
          <DialogDescription>
            明文已留存，可随时在列表展开 / 复制；建议立即保存到安全位置。
          </DialogDescription>
        </DialogHeader>
        <div className="bg-warm-2/40 overflow-hidden rounded-lg border border-stone-200/80">
          <div className="flex items-center justify-between border-b border-stone-200/70 bg-white/40 px-3 py-1.5">
            <span className="text-[11.5px] font-medium text-stone-700">API Key（明文）</span>
            <button
              type="button"
              onClick={copy}
              className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-stone-500 transition hover:bg-stone-100 hover:text-stone-900"
            >
              <Copy className="h-3 w-3" />
              复制
            </button>
          </div>
          <pre className="overflow-x-auto px-3.5 py-3 font-mono text-[12.5px] leading-relaxed break-all whitespace-pre-wrap text-stone-800">
            {plain?.plain_key}
          </pre>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={copy}>
            <Copy className="h-4 w-4" /> 复制
          </Button>
          <Button onClick={onClose}>已保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

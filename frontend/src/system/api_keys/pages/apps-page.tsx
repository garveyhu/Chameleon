/** Key 管理：扁平 API Key 列表 + 新建 / 撤销 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Copy, Eye, EyeOff, KeyRound, Plus } from 'lucide-react';

import { ConfirmDialog } from '@/core/components/common/confirm-dialog';
import { EmptyState } from '@/core/components/common/empty-state';
import {
  DataTable,
  type DataTableColumn,
  SectionCard,
  TablePagination,
  TableToolbar,
} from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
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
import type { EntityId } from '@/core/types/api';
import { formatRelative } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import { apiKeyApi } from '@/system/api_keys/services/app';
import type {
  ApiKeyCreated,
  ApiKeyItem,
  ApiKeyScopeType,
  CreateApiKeyRequest,
} from '@/system/api_keys/types/app';

// scope 中文标签 + 徽标配色
const SCOPE_META: Record<ApiKeyScopeType, { label: string; variant: 'primary' | 'success' | 'warning' }> = {
  global: { label: '通用', variant: 'primary' },
  app: { label: '应用', variant: 'success' },
  kb: { label: '知识库', variant: 'warning' },
};

const scopeMeta = (t: string) =>
  SCOPE_META[(t as ApiKeyScopeType) in SCOPE_META ? (t as ApiKeyScopeType) : 'global'];

export const AppsPage = () => {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [createOpen, setCreateOpen] = useState(false);
  const [revokeKey, setRevokeKey] = useState<ApiKeyItem | null>(null);
  const [plain, setPlain] = useState<ApiKeyCreated | null>(null);

  const listQ = useQuery({
    queryKey: ['api-keys', page, pageSize],
    queryFn: () => apiKeyApi.list({ page, page_size: pageSize, include_revoked: true }),
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

  const columns: DataTableColumn<ApiKeyItem>[] = [
    {
      key: 'name',
      header: t('common.name'),
      render: k => <span className="font-medium text-stone-900">{k.name}</span>,
    },
    {
      key: 'scope',
      header: '作用域',
      width: 80,
      render: k => {
        const m = scopeMeta(k.scope_type);
        return <Badge variant={m.variant}>{m.label}</Badge>;
      },
    },
    {
      key: 'scope_ref',
      header: '目标',
      render: k =>
        k.scope_ref ? (
          <span className="font-mono text-[11.5px] text-stone-600">{k.scope_ref}</span>
        ) : (
          <span className="text-stone-300">—</span>
        ),
    },
    {
      key: 'key',
      header: '密钥',
      width: 220,
      render: k => <KeyCopyCell prefix={k.key_prefix} plain={k.plain_key} />,
    },
    {
      key: 'app_id',
      header: '来源标签',
      render: k => <span className="font-mono text-[11px] text-stone-400">{k.app_id}</span>,
    },
    {
      key: 'limits',
      header: '配额',
      width: 150,
      render: k => (
        <span className="tnum font-mono text-[11.5px] text-stone-500">
          QPM {k.qpm_limit ?? '∞'} · QPD {k.qpd_limit ?? '∞'}
        </span>
      ),
    },
    {
      key: 'status',
      header: t('common.status'),
      width: 80,
      render: k =>
        k.revoked_at ? (
          <Badge variant="danger">已撤销</Badge>
        ) : (
          <Badge variant="success">活跃</Badge>
        ),
    },
    {
      key: 'last_used_at',
      header: '最近使用',
      width: 120,
      render: k => (
        <span className="tnum font-mono text-[11.5px] text-stone-500">
          {k.last_used_at ? formatRelative(k.last_used_at) : '从未'}
        </span>
      ),
    },
    {
      key: 'actions',
      header: t('common.actions'),
      align: 'right',
      width: 90,
      render: k =>
        k.revoked_at ? null : (
          <Button
            size="sm"
            variant="ghost"
            className="text-red-600"
            onClick={() => setRevokeKey(k)}
          >
            撤销
          </Button>
        ),
    },
  ];

  return (
    <div>
      <SectionCard>
        <TableToolbar
          title={t('page.api_keys_title')}
          extra={
            <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> {t('common.create')}
            </Button>
          }
        />
        <DataTable
          columns={columns}
          rows={listQ.data?.items || []}
          rowKey="id"
          loading={listQ.isLoading}
          emptyText={
            <EmptyState
              icon={<KeyRound strokeWidth={1.5} />}
              title={t('empty.api_keys')}
              action={
                <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
                  <Plus className="h-3.5 w-3.5" /> {t('common.create')}
                </Button>
              }
            />
          }
        />
        <TablePagination
          page={page}
          pageSize={pageSize}
          total={listQ.data?.total || 0}
          onPageChange={setPage}
          onPageSizeChange={s => {
            setPageSize(s);
            setPage(1);
          }}
        />
      </SectionCard>

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

/** 密钥单元格：默认掩码，点眼睛展开全文，点复制拷全文（老数据无明文只显前缀） */
const KeyCopyCell = ({ prefix, plain }: { prefix: string; plain: string | null }) => {
  const [shown, setShown] = useState(false);
  const [copied, setCopied] = useState(false);
  const copy = () => {
    if (!plain) return;
    void navigator.clipboard.writeText(plain).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="flex items-center gap-1.5">
      <code className="font-mono text-xs text-stone-600">
        {plain ? (shown ? plain : `${prefix}${'•'.repeat(8)}`) : `${prefix}...`}
      </code>
      {plain && (
        <>
          <button
            type="button"
            onClick={() => setShown(s => !s)}
            title={shown ? '隐藏' : '显示'}
            className="text-stone-400 transition hover:text-stone-700"
          >
            {shown ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
          <button
            type="button"
            onClick={copy}
            title="复制"
            className="text-stone-400 transition hover:text-stone-700"
          >
            {copied ? (
              <Check className="h-3.5 w-3.5 text-emerald-500" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </button>
        </>
      )}
    </div>
  );
};

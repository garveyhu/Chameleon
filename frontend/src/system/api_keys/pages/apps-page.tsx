/** Key 管理：按作用域分组的现代卡片 + 新建 / 撤销 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen, Bot, Copy, Globe, KeyRound, Plus, Search } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ConfirmDialog } from '@/core/components/common/confirm-dialog';
import { EmptyState } from '@/core/components/common/empty-state';
import { MiniStat } from '@/core/components/common/mini-stat';
import { TablePagination } from '@/core/components/table';
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
import { KeyDetailDialog } from '@/system/api_keys/components/key-detail-dialog';
import { KeyRow } from '@/system/api_keys/components/key-row';
import { apiKeyApi } from '@/system/api_keys/services/app';
import type {
  ApiKeyCreated,
  ApiKeyItem,
  ApiKeyScopeType,
  CreateApiKeyRequest,
} from '@/system/api_keys/types/app';

export const AppsPage = () => {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [revokeKey, setRevokeKey] = useState<ApiKeyItem | null>(null);
  const [detailKey, setDetailKey] = useState<ApiKeyItem | null>(null);
  const [plain, setPlain] = useState<ApiKeyCreated | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(15);
  const [search, setSearch] = useState('');
  const [scopeFilter, setScopeFilter] = useState<'all' | ApiKeyScopeType>('all');

  const listQ = useQuery({
    queryKey: ['api-keys', page, pageSize, search, scopeFilter],
    queryFn: () =>
      apiKeyApi.list({
        page,
        page_size: pageSize,
        q: search.trim() || undefined,
        scope_type: scopeFilter === 'all' ? undefined : scopeFilter,
      }),
  });

  // 概览统计走独立查询（全部未撤销，不受列表过滤影响）
  const statsQ = useQuery({
    queryKey: ['api-keys-stats'],
    queryFn: () => apiKeyApi.list({ page: 1, page_size: 100 }),
  });

  const createMut = useMutation({
    mutationFn: apiKeyApi.create,
    onSuccess: created => {
      qc.invalidateQueries({ queryKey: ['api-keys'] });
      qc.invalidateQueries({ queryKey: ['api-keys-stats'] });
      setCreateOpen(false);
      setPlain(created);
    },
  });

  const revokeMut = useMutation({
    mutationFn: (id: EntityId) => apiKeyApi.revoke(id),
    onSuccess: () => {
      toast.success('密钥已撤销');
      qc.invalidateQueries({ queryKey: ['api-keys'] });
      qc.invalidateQueries({ queryKey: ['api-keys-stats'] });
      setRevokeKey(null);
      setDetailKey(null);
    },
  });

  const items = listQ.data?.items ?? [];
  const total = listQ.data?.total ?? 0;
  const statItems = statsQ.data?.items ?? [];
  const filtered = search.trim() !== '' || scopeFilter !== 'all';

  const onSearch = (v: string) => {
    setSearch(v);
    setPage(1);
  };
  const onScope = (v: string) => {
    setScopeFilter(v as 'all' | ApiKeyScopeType);
    setPage(1);
  };

  return (
    <div className="space-y-5">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-[16px] font-semibold text-stone-900">
            {t('page.api_keys_title')}
          </h1>
          <p className="mt-0.5 text-[12px] text-stone-500">
            对外签发的访问密钥 —— 在此查询、查看与撤销
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="h-3.5 w-3.5" /> {t('common.create')}
        </Button>
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MiniStat label="密钥总数" value={statsQ.data?.total ?? 0} icon={KeyRound} tone="primary" />
        <MiniStat
          label="应用密钥"
          value={statItems.filter(k => k.scope_type === 'app').length}
          icon={Bot}
          tone="success"
        />
        <MiniStat
          label="知识库密钥"
          value={statItems.filter(k => k.scope_type === 'kb').length}
          icon={BookOpen}
          tone="warning"
        />
        <MiniStat
          label="通用密钥"
          value={statItems.filter(k => k.scope_type === 'global').length}
          icon={Globe}
          tone="sky"
        />
      </div>

      <div className="flex items-center gap-2">
        <div className="relative max-w-xs flex-1">
          <Search className="absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-stone-400" />
          <Input
            value={search}
            onChange={e => onSearch(e.target.value)}
            placeholder="搜索名称 / 来源 / 目标"
            className="pl-8"
          />
        </div>
        <Select value={scopeFilter} onValueChange={onScope}>
          <SelectTrigger className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部作用域</SelectItem>
            <SelectItem value="app">应用</SelectItem>
            <SelectItem value="kb">知识库</SelectItem>
            <SelectItem value="global">通用</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {listQ.isLoading ? (
        <div className="divide-y divide-stone-100 overflow-hidden rounded-xl border border-stone-200">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-12 animate-pulse bg-stone-50" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={<KeyRound strokeWidth={1.5} />}
          title={filtered ? '没有匹配的密钥' : t('empty.api_keys')}
          action={
            !filtered ? (
              <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
                <Plus className="h-3.5 w-3.5" /> {t('common.create')}
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="divide-y divide-stone-100 overflow-hidden rounded-xl border border-stone-200 bg-[var(--color-paper)]">
            {items.map(k => (
              <KeyRow
                key={String(k.id)}
                apiKey={k}
                onOpen={() => setDetailKey(k)}
                onRevoke={() => setRevokeKey(k)}
              />
            ))}
          </div>
          <TablePagination
            page={page}
            pageSize={pageSize}
            total={total}
            onPageChange={setPage}
            onPageSizeChange={s => {
              setPageSize(s);
              setPage(1);
            }}
          />
        </>
      )}

      <KeyDetailDialog
        apiKey={detailKey}
        onClose={() => setDetailKey(null)}
        onRevoke={() => {
          setRevokeKey(detailKey);
          setDetailKey(null);
        }}
      />

      <CreateKeyModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={createMut.mutate}
        loading={createMut.isPending}
      />

      <ConfirmDialog
        open={!!revokeKey}
        title="撤销密钥"
        description={`撤销后用此密钥的调用将被拒绝，且不可恢复（${revokeKey?.name}）。`}
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
  const [desc, setDesc] = useState('');

  const reset = () => {
    setName('');
    setAppId('');
    setScopeType('global');
    setScopeRef('');
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
          <ModalTitle>新建密钥</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div className="space-y-1.5">
            <Label>名称</Label>
            <Input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="如 生产环境 / 移动端 / CI"
            />
            <p className="text-[11px] text-stone-500">仅用于识别与撤销，不是密钥本身</p>
          </div>
          <div className="space-y-1.5">
            <Label>作用域</Label>
            <Select value={scopeType} onValueChange={v => setScopeType(v as ApiKeyScopeType)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="global">通用（所有服务）</SelectItem>
                <SelectItem value="app">应用（绑定某智能体）</SelectItem>
                <SelectItem value="kb">知识库（绑定某知识库）</SelectItem>
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

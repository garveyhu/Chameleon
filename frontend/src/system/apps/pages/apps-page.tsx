/** apps + api_keys 管理页 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Copy, Eye, EyeOff, Key, KeyRound, Plus, Trash2 } from 'lucide-react';

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
  Sheet,
  SheetBody,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import { Textarea } from '@/core/components/ui/textarea';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import { apiKeyApi, appApi } from '@/system/apps/services/app';
import type { ApiKeyCreated, AppItem } from '@/system/apps/types/app';

export const AppsPage = () => {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [createOpen, setCreateOpen] = useState(false);
  const [keysApp, setKeysApp] = useState<AppItem | null>(null);
  const [delApp, setDelApp] = useState<AppItem | null>(null);

  const listQ = useQuery({
    queryKey: ['apps', page, pageSize],
    queryFn: () => appApi.list({ page, page_size: pageSize }),
  });

  const createMut = useMutation({
    mutationFn: appApi.create,
    onSuccess: () => {
      toast.success('应用已创建');
      qc.invalidateQueries({ queryKey: ['apps'] });
      setCreateOpen(false);
    },
  });

  const delMut = useMutation({
    mutationFn: (id: import('@/core/types/api').EntityId) => appApi.delete(id),
    onSuccess: () => {
      toast.success('应用已删除');
      qc.invalidateQueries({ queryKey: ['apps'] });
      setDelApp(null);
    },
  });

  const columns: DataTableColumn<AppItem>[] = [
    {
      key: 'app_key',
      header: t('table.app_key'),
      render: a => <span className="font-mono text-[12px] text-stone-700">{a.app_key}</span>,
    },
    {
      key: 'name',
      header: t('common.name'),
      render: a => <span className="font-medium text-stone-900">{a.name}</span>,
    },
    {
      key: 'status',
      header: t('common.status'),
      width: 80,
      render: a => (
        <Badge variant={a.status === 'active' ? 'success' : 'warning'}>
          {a.status === 'active' ? t('common.active') : t('common.suspended')}
        </Badge>
      ),
    },
    {
      key: 'limits',
      header: '配额',
      width: 160,
      render: a => (
        <span className="tnum font-mono text-[11.5px] text-stone-500">
          QPM {a.qpm_limit ?? '∞'} · QPD {a.qpd_limit ?? '∞'}
        </span>
      ),
    },
    {
      key: 'created_at',
      header: t('common.created_at'),
      width: 160,
      render: a => (
        <span className="tnum font-mono text-[11.5px] text-stone-500">
          {formatDateTime(a.created_at)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: t('common.actions'),
      align: 'right',
      width: 130,
      render: a => (
        <div className="inline-flex items-center gap-0.5">
          <button
            type="button"
            title="API Keys"
            className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-[11.5px] text-stone-600 hover:bg-stone-200 hover:text-stone-900"
            onClick={() => setKeysApp(a)}
          >
            <KeyRound className="h-3.5 w-3.5" /> Keys
          </button>
          <button
            type="button"
            title="删除"
            className="rounded p-1 text-stone-600 hover:bg-red-100 hover:text-red-600"
            onClick={() => setDelApp(a)}
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
          title={t('page.apps_title')}
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
              icon={<Key strokeWidth={1.5} />}
              title={t('empty.apps')}
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

      <CreateAppModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={createMut.mutate}
        loading={createMut.isPending}
      />
      <ApiKeysSheet app={keysApp} onClose={() => setKeysApp(null)} />
      <ConfirmDialog
        open={!!delApp}
        title="删除应用"
        description={`删除应用 ${delApp?.app_key} 后所有 API key、会话、调用记录都会级联清除。`}
        variant="danger"
        confirmText="删除"
        onConfirm={() => delApp && delMut.mutate(delApp.id)}
        onCancel={() => setDelApp(null)}
      />
    </div>
  );
};

// ── 创建应用 ───────────────────────────────────────────────

const CreateAppModal = ({
  open,
  onClose,
  onSubmit,
  loading,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (req: { app_key: string; name: string; description?: string }) => void;
  loading: boolean;
}) => {
  const [k, setK] = useState('');
  const [n, setN] = useState('');
  const [d, setD] = useState('');

  return (
    <Modal
      open={open}
      onOpenChange={o => {
        if (!o) {
          setK('');
          setN('');
          setD('');
          onClose();
        }
      }}
    >
      <ModalContent size="md">
        <ModalHeader>
          <ModalTitle>新建应用</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div className="space-y-1.5">
            <Label>应用标识</Label>
            <Input
              value={k}
              onChange={e => setK(e.target.value)}
              placeholder="my-side-project"
              className="font-mono text-[12.5px]"
            />
            <p className="text-[11px] text-stone-500">
              业务方调用时作为 <code className="font-mono">app_id</code> 传入；建议
              kebab-case，创建后不可改。
            </p>
          </div>
          <div className="space-y-1.5">
            <Label>名称</Label>
            <Input value={n} onChange={e => setN(e.target.value)} placeholder="我的项目" />
          </div>
          <div className="space-y-1.5">
            <Label>描述</Label>
            <Textarea value={d} onChange={e => setD(e.target.value)} rows={3} />
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button
            disabled={loading || !k || !n}
            onClick={() => onSubmit({ app_key: k, name: n, description: d || undefined })}
          >
            {loading ? '创建中...' : '创建'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

// ── API Keys 子表 ──────────────────────────────────────────

const ApiKeysSheet = ({ app, onClose }: { app: AppItem | null; onClose: () => void }) => {
  const qc = useQueryClient();
  const [newKeyName, setNewKeyName] = useState('');
  const [newScopes, setNewScopes] = useState('');
  const [plain, setPlain] = useState<ApiKeyCreated | null>(null);

  const keysQ = useQuery({
    queryKey: ['app-keys', app?.id],
    queryFn: () => (app ? appApi.listApiKeys(app.id) : Promise.resolve([])),
    enabled: !!app,
  });

  const createKeyMut = useMutation({
    mutationFn: () =>
      apiKeyApi.create({
        app_id: app!.app_key,
        name: newKeyName,
        scopes: newScopes
          ? newScopes
              .split(',')
              .map(s => s.trim())
              .filter(Boolean)
          : [],
      }),
    onSuccess: created => {
      qc.invalidateQueries({ queryKey: ['app-keys'] });
      setPlain(created);
      setNewKeyName('');
      setNewScopes('');
    },
  });

  const revokeMut = useMutation({
    mutationFn: (id: import('@/core/types/api').EntityId) => apiKeyApi.revoke(id),
    onSuccess: () => {
      toast.success('Key 已撤销');
      qc.invalidateQueries({ queryKey: ['app-keys'] });
    },
  });

  return (
    <>
      <Sheet open={!!app} onOpenChange={o => !o && onClose()}>
        <SheetContent width="w-[640px]">
          <SheetHeader>
            <SheetTitle>{app?.name} · API Keys</SheetTitle>
          </SheetHeader>
          <SheetBody className="space-y-6">
            {/* 新建 key */}
            <div className="rounded-lg border border-stone-200 bg-stone-50 p-4">
              <div className="mb-1 text-xs font-semibold text-stone-500 uppercase">
                签发新 API Key
              </div>
              <p className="mb-3 text-[11.5px] text-stone-500">
                密钥由系统随机生成，签发后留存明文，可随时在下方列表展开 / 复制。
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">标识名</Label>
                  <Input
                    value={newKeyName}
                    onChange={e => setNewKeyName(e.target.value)}
                    placeholder="prod / ci / mobile-app"
                  />
                  <p className="mt-1 text-[10.5px] text-stone-400">
                    只用于识别和撤销，不是密钥本身
                  </p>
                </div>
                <div>
                  <Label className="text-xs">scopes（逗号分隔）</Label>
                  <Input
                    value={newScopes}
                    onChange={e => setNewScopes(e.target.value)}
                    placeholder="留空 = 仅业务接口；admin = 含管理接口"
                  />
                  <p className="mt-1 text-[10.5px] text-stone-400">
                    例：<code className="font-mono">admin</code> 给后台脚本用
                  </p>
                </div>
              </div>
              <Button
                className="mt-3"
                size="sm"
                disabled={!newKeyName || createKeyMut.isPending}
                onClick={() => createKeyMut.mutate()}
              >
                {createKeyMut.isPending ? '签发中...' : '签发并生成密钥'}
              </Button>
            </div>

            {/* 已签发 key 列表 */}
            <div>
              <div className="mb-2 text-xs font-semibold text-stone-500 uppercase">已签发</div>
              <table className="w-full text-sm">
                <thead className="text-xs text-stone-500">
                  <tr>
                    <th className="py-1 text-left">前缀</th>
                    <th className="py-1 text-left">名称</th>
                    <th className="py-1 text-left">scopes</th>
                    <th className="py-1 text-left">状态</th>
                    <th />
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {(keysQ.data || []).map(k => (
                    <tr key={k.id}>
                      <td className="py-2">
                        <KeyCopyCell prefix={k.key_prefix} plain={k.plain_key} />
                      </td>
                      <td>{k.name}</td>
                      <td>
                        {k.scopes.length === 0 ? (
                          '—'
                        ) : (
                          <div className="flex gap-1">
                            {k.scopes.map(s => (
                              <Badge key={s} variant="outline">
                                {s}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </td>
                      <td>
                        {k.revoked_at ? (
                          <Badge variant="danger">已撤销</Badge>
                        ) : (
                          <Badge variant="success">活跃</Badge>
                        )}
                      </td>
                      <td className="text-right">
                        {!k.revoked_at && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-red-600"
                            onClick={() => revokeMut.mutate(k.id)}
                          >
                            撤销
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SheetBody>
          <SheetFooter>
            <Button variant="ghost" onClick={onClose}>
              关闭
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>

      {/* 新签发明文 token（也可随时在列表展开复制） */}
      <Dialog open={!!plain} onOpenChange={o => !o && setPlain(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新 API Key 已签发</DialogTitle>
            <DialogDescription>
              明文已留存，可随时在下方列表展开 / 复制；建议立即保存到安全位置。
            </DialogDescription>
          </DialogHeader>
          <div className="bg-warm-2/40 overflow-hidden rounded-lg border border-stone-200/80">
            <div className="flex items-center justify-between border-b border-stone-200/70 bg-white/40 px-3 py-1.5">
              <span className="text-[11.5px] font-medium text-stone-700">API Key（明文）</span>
              <button
                type="button"
                onClick={() => {
                  if (plain?.plain_key) {
                    navigator.clipboard.writeText(plain.plain_key);
                    toast.success('已复制');
                  }
                }}
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
            <Button
              variant="outline"
              onClick={() => {
                if (plain?.plain_key) {
                  navigator.clipboard.writeText(plain.plain_key);
                  toast.success('已复制');
                }
              }}
            >
              <Copy className="h-4 w-4" /> 复制
            </Button>
            <Button onClick={() => setPlain(null)}>已保存</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

/** 列表里的密钥单元格：默认掩码，点眼睛展开全文，点复制拷全文（老数据无明文只显前缀） */
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

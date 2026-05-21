/** apps + api_keys 管理页 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy, KeyRound, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

import { ConfirmDialog } from '@/core/components/common/confirm-dialog';
import { DataTable, type DataTableColumn } from '@/core/components/common/data-table';
import { PageHeader } from '@/core/components/common/page-header';
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
  Sheet,
  SheetBody,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import { Textarea } from '@/core/components/ui/textarea';
import { formatDateTime } from '@/core/lib/format';
import { apiKeyApi, appApi } from '@/system/apps/services/app';
import type { ApiKeyCreated, AppItem } from '@/system/apps/types/app';

export const AppsPage = () => {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [keysApp, setKeysApp] = useState<AppItem | null>(null);
  const [delApp, setDelApp] = useState<AppItem | null>(null);

  const listQ = useQuery({
    queryKey: ['apps', page],
    queryFn: () => appApi.list({ page, page_size: 20 }),
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
    mutationFn: (id: number) => appApi.delete(id),
    onSuccess: () => {
      toast.success('应用已删除');
      qc.invalidateQueries({ queryKey: ['apps'] });
      setDelApp(null);
    },
  });

  const columns: DataTableColumn<AppItem>[] = [
    { key: 'app_key', title: 'app_key', render: a => <span className="font-mono">{a.app_key}</span> },
    { key: 'name', title: '名称' },
    {
      key: 'status',
      title: '状态',
      render: a => (
        <Badge variant={a.status === 'active' ? 'success' : 'warning'}>
          {a.status === 'active' ? '活跃' : '挂起'}
        </Badge>
      ),
    },
    {
      key: 'limits',
      title: '配额',
      render: a => (
        <span className="text-xs text-stone-500">
          QPM {a.qpm_limit ?? '∞'} · QPD {a.qpd_limit ?? '∞'}
        </span>
      ),
    },
    {
      key: 'created_at',
      title: '创建于',
      render: a => <span className="text-xs text-stone-500">{formatDateTime(a.created_at)}</span>,
    },
    {
      key: 'actions',
      title: '操作',
      align: 'right',
      width: '180px',
      render: a => (
        <div className="flex justify-end gap-1">
          <Button size="sm" variant="ghost" onClick={() => setKeysApp(a)}>
            <KeyRound className="h-3.5 w-3.5" /> API Keys
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="text-red-600 hover:bg-red-50"
            onClick={() => setDelApp(a)}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="应用 & API Key"
        description="业务方应用与对外凭证管理"
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> 新建应用
          </Button>
        }
      />
      <DataTable
        columns={columns}
        data={listQ.data?.items || []}
        loading={listQ.isLoading}
        pagination={{ page, pageSize: 20, total: listQ.data?.total || 0, onPageChange: setPage }}
      />

      <CreateAppSheet
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

const CreateAppSheet = ({
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
    <Sheet
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
      <SheetContent>
        <SheetHeader>
          <SheetTitle>新建应用</SheetTitle>
        </SheetHeader>
        <SheetBody className="space-y-4">
          <div className="space-y-1.5">
            <Label>app_key（唯一标识，业务方调用用）</Label>
            <Input value={k} onChange={e => setK(e.target.value)} placeholder="my-side-project" />
          </div>
          <div className="space-y-1.5">
            <Label>名称</Label>
            <Input value={n} onChange={e => setN(e.target.value)} placeholder="我的项目" />
          </div>
          <div className="space-y-1.5">
            <Label>描述</Label>
            <Textarea value={d} onChange={e => setD(e.target.value)} rows={3} />
          </div>
        </SheetBody>
        <SheetFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button
            disabled={loading || !k || !n}
            onClick={() => onSubmit({ app_key: k, name: n, description: d || undefined })}
          >
            {loading ? '创建中...' : '创建'}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
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
    mutationFn: (id: number) => apiKeyApi.revoke(id),
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
              <div className="mb-3 text-xs font-semibold uppercase text-stone-500">签发新 key</div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Key 名称</Label>
                  <Input
                    value={newKeyName}
                    onChange={e => setNewKeyName(e.target.value)}
                    placeholder="prod-key"
                  />
                </div>
                <div>
                  <Label className="text-xs">scopes（逗号分隔，留空仅业务）</Label>
                  <Input
                    value={newScopes}
                    onChange={e => setNewScopes(e.target.value)}
                    placeholder="admin"
                  />
                </div>
              </div>
              <Button
                className="mt-3"
                size="sm"
                disabled={!newKeyName || createKeyMut.isPending}
                onClick={() => createKeyMut.mutate()}
              >
                {createKeyMut.isPending ? '签发中...' : '签发'}
              </Button>
            </div>

            {/* 已签发 key 列表 */}
            <div>
              <div className="mb-2 text-xs font-semibold uppercase text-stone-500">已签发</div>
              <table className="w-full text-sm">
                <thead className="text-xs text-stone-500">
                  <tr>
                    <th className="text-left py-1">前缀</th>
                    <th className="text-left py-1">名称</th>
                    <th className="text-left py-1">scopes</th>
                    <th className="text-left py-1">状态</th>
                    <th />
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {(keysQ.data || []).map(k => (
                    <tr key={k.id}>
                      <td className="py-2 font-mono text-xs">{k.key_prefix}...</td>
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

      {/* 新签发明文 token 仅一次显示 */}
      <Dialog open={!!plain} onOpenChange={o => !o && setPlain(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新 API Key 已签发</DialogTitle>
            <DialogDescription>
              这是<strong className="text-red-600">唯一一次</strong>看到明文 token 的机会，请立即保存。
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-md bg-stone-900 p-3 font-mono text-xs text-emerald-300 break-all">
            {plain?.plain_key}
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

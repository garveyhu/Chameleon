/** providers 管理页 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Plus, Trash2, Zap } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

import { ConfirmDialog } from '@/core/components/common/confirm-dialog';
import {
  DataTable,
  type DataTableColumn,
  SectionCard,
  TableToolbar,
} from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
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
  Sheet,
  SheetBody,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import { providerApi } from '@/system/providers/services/provider';
import type { ProviderItem } from '@/system/providers/types/provider';

export const ProvidersPage = () => {
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [delProv, setDelProv] = useState<ProviderItem | null>(null);

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
    mutationFn: (id: number) => providerApi.delete(id),
    onSuccess: () => {
      toast.success('已删除');
      qc.invalidateQueries({ queryKey: ['providers'] });
      setDelProv(null);
    },
  });

  const testMut = useMutation({
    mutationFn: (id: number) => providerApi.test(id),
    onSuccess: data => toast[data.ok ? 'success' : 'error'](data.detail),
  });

  const columns: DataTableColumn<ProviderItem>[] = [
    { key: 'code', header: 'code', width: 140, render: p => <span className="font-mono text-[11.5px] text-stone-700">{p.code}</span> },
    { key: 'name', header: '名称', render: p => <span className="font-medium text-stone-900">{p.name}</span> },
    { key: 'kind', header: '类型', width: 100, render: p => <Badge variant="primary">{p.kind}</Badge> },
    { key: 'base_url', header: 'base_url', render: p => <span className="font-mono text-[11.5px] text-stone-600">{p.base_url || '—'}</span> },
    {
      key: 'api_key',
      header: 'API Key',
      width: 90,
      render: p => p.has_api_key ? <Badge variant="success">已配置</Badge> : <Badge variant="warning">未配置</Badge>,
    },
    {
      key: 'enabled',
      header: '启用',
      width: 60,
      align: 'center',
      render: p => p.enabled ? <CheckCircle2 className="mx-auto h-4 w-4 text-emerald-600" /> : <span className="text-stone-400">—</span>,
    },
    {
      key: 'actions',
      header: '操作',
      align: 'right',
      width: 110,
      render: p => (
        <div className="inline-flex items-center gap-0.5">
          <button
            type="button"
            title="测试连通性"
            className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-[11.5px] text-stone-600 hover:bg-stone-200 hover:text-stone-900 disabled:opacity-50"
            onClick={() => testMut.mutate(p.id)}
            disabled={testMut.isPending}
          >
            <Zap className="h-3.5 w-3.5" /> 测试
          </button>
          <button
            type="button"
            title="删除"
            className="rounded p-1 text-stone-600 hover:bg-red-100 hover:text-red-600"
            onClick={() => setDelProv(p)}
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
          title="Providers"
          extra={
            <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> 新建
            </Button>
          }
        />
        <DataTable columns={columns} rows={listQ.data || []} rowKey="id" loading={listQ.isLoading} emptyText="还没有 Provider" />
      </SectionCard>
      <CreateProviderSheet
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
    </div>
  );
};

const CreateProviderSheet = ({
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
    <Sheet
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
      <SheetContent>
        <SheetHeader>
          <SheetTitle>新建 Provider</SheetTitle>
        </SheetHeader>
        <SheetBody className="space-y-4">
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
        </SheetBody>
        <SheetFooter>
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
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
};

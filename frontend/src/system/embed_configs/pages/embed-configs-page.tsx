/** 嵌入式配置管理页 + 嵌入代码生成器 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Code2, Copy, Plus, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { toast } from 'sonner';

import { ConfirmDialog } from '@/core/components/common/confirm-dialog';
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
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/core/components/ui/dialog';
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
import { Textarea } from '@/core/components/ui/textarea';
import { agentApi } from '@/system/agents/services/agent';
import { appApi } from '@/system/apps/services/app';
import { embedConfigApi } from '@/system/embed_configs/services/embed';
import type { EmbedConfigItem } from '@/system/embed_configs/types/embed';

export const EmbedConfigsPage = () => {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [createOpen, setCreateOpen] = useState(false);
  const [snippetCfg, setSnippetCfg] = useState<EmbedConfigItem | null>(null);
  const [delCfg, setDelCfg] = useState<EmbedConfigItem | null>(null);

  const listQ = useQuery({
    queryKey: ['embed-configs', page, pageSize],
    queryFn: () => embedConfigApi.list({ page, page_size: pageSize }),
  });

  const createMut = useMutation({
    mutationFn: embedConfigApi.create,
    onSuccess: () => {
      toast.success('嵌入配置已创建');
      qc.invalidateQueries({ queryKey: ['embed-configs'] });
      setCreateOpen(false);
    },
  });

  const delMut = useMutation({
    mutationFn: (id: number) => embedConfigApi.delete(id),
    onSuccess: () => {
      toast.success('已删除');
      qc.invalidateQueries({ queryKey: ['embed-configs'] });
      setDelCfg(null);
    },
  });

  const columns: DataTableColumn<EmbedConfigItem>[] = [
    {
      key: 'embed_key',
      header: 'embed_key',
      width: 200,
      render: e => <span className="font-mono text-[11.5px] text-stone-700">{e.embed_key}</span>,
    },
    { key: 'name', header: '名称', render: e => <span className="font-medium text-stone-900">{e.name}</span> },
    {
      key: 'allowed_origins',
      header: 'origins',
      render: e =>
        e.allowed_origins && e.allowed_origins.length ? (
          <div className="flex flex-wrap gap-1">
            {e.allowed_origins.slice(0, 2).map(o => (
              <Badge key={o} variant="outline">
                {o.replace(/^https?:\/\//, '')}
              </Badge>
            ))}
            {e.allowed_origins.length > 2 && (
              <Badge variant="outline">+{e.allowed_origins.length - 2}</Badge>
            )}
          </div>
        ) : (
          <Badge variant="warning">未配置</Badge>
        ),
    },
    {
      key: 'enabled',
      header: '启用',
      width: 70,
      render: e => e.enabled ? <Badge variant="success">是</Badge> : <Badge variant="warning">否</Badge>,
    },
    {
      key: 'actions',
      header: '操作',
      align: 'right',
      width: 130,
      render: e => (
        <div className="inline-flex items-center gap-0.5">
          <button
            type="button"
            title="嵌入代码"
            className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-[11.5px] text-stone-600 hover:bg-stone-200 hover:text-stone-900"
            onClick={() => setSnippetCfg(e)}
          >
            <Code2 className="h-3.5 w-3.5" /> 代码
          </button>
          <button
            type="button"
            title="删除"
            className="rounded p-1 text-stone-600 hover:bg-red-100 hover:text-red-600"
            onClick={() => setDelCfg(e)}
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
          title="嵌入式智能体"
          extra={
            <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> 新建
            </Button>
          }
        />
        <DataTable
          columns={columns}
          rows={listQ.data?.items || []}
          rowKey="id"
          loading={listQ.isLoading}
          emptyText="还没有嵌入式配置"
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

      <CreateEmbedSheet
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={createMut.mutate}
        loading={createMut.isPending}
      />
      <SnippetDialog cfg={snippetCfg} onClose={() => setSnippetCfg(null)} />
      <ConfirmDialog
        open={!!delCfg}
        title="删除嵌入配置"
        description={`删除后业务方网页里的 widget 立即失效。`}
        variant="danger"
        confirmText="删除"
        onConfirm={() => delCfg && delMut.mutate(delCfg.id)}
        onCancel={() => setDelCfg(null)}
      />
    </div>
  );
};

const CreateEmbedSheet = ({
  open,
  onClose,
  onSubmit,
  loading,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (req: {
    name: string;
    agent_id: number;
    app_id: number;
    allowed_origins?: string[];
  }) => void;
  loading: boolean;
}) => {
  const [name, setName] = useState('');
  const [agentId, setAgentId] = useState('');
  const [appId, setAppId] = useState('');
  const [origins, setOrigins] = useState('');

  const agentsQ = useQuery({ queryKey: ['agents', 'all'], queryFn: () => agentApi.list() });
  const appsQ = useQuery({
    queryKey: ['apps', 'all'],
    queryFn: () => appApi.list({ page: 1, page_size: 100 }),
  });

  return (
    <Sheet
      open={open}
      onOpenChange={o => {
        if (!o) {
          setName('');
          setAgentId('');
          setAppId('');
          setOrigins('');
          onClose();
        }
      }}
    >
      <SheetContent>
        <SheetHeader>
          <SheetTitle>新建嵌入配置</SheetTitle>
        </SheetHeader>
        <SheetBody className="space-y-4">
          <div className="space-y-1.5">
            <Label>名称</Label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="官网客服" />
          </div>
          <div className="space-y-1.5">
            <Label>关联 Agent</Label>
            <Select value={agentId} onValueChange={setAgentId}>
              <SelectTrigger>
                <SelectValue placeholder="选择 agent" />
              </SelectTrigger>
              <SelectContent>
                {(agentsQ.data || []).map(a => (
                  <SelectItem key={a.id} value={String(a.id)}>
                    {a.agent_key} · {a.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>关联 App</Label>
            <Select value={appId} onValueChange={setAppId}>
              <SelectTrigger>
                <SelectValue placeholder="选择 app" />
              </SelectTrigger>
              <SelectContent>
                {(appsQ.data?.items || []).map(a => (
                  <SelectItem key={a.id} value={String(a.id)}>
                    {a.app_key} · {a.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Origin 白名单（每行一个，留空拒绝所有跨域）</Label>
            <Textarea
              value={origins}
              onChange={e => setOrigins(e.target.value)}
              rows={4}
              placeholder="https://example.com&#10;https://app.example.com"
              className="font-mono text-xs"
            />
          </div>
        </SheetBody>
        <SheetFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button
            disabled={loading || !name || !agentId || !appId}
            onClick={() =>
              onSubmit({
                name,
                agent_id: Number(agentId),
                app_id: Number(appId),
                allowed_origins: origins
                  ? origins
                      .split('\n')
                      .map(o => o.trim())
                      .filter(Boolean)
                  : [],
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

const SnippetDialog = ({
  cfg,
  onClose,
}: {
  cfg: EmbedConfigItem | null;
  onClose: () => void;
}) => {
  const base = useMemo(() => window.location.origin, []);
  const widget = cfg
    ? `<script src="${base}/widget.js" data-embed-key="${cfg.embed_key}" defer></script>`
    : '';
  const iframe = cfg
    ? `<iframe src="${base}/embed/${cfg.embed_key}" style="width:400px;height:600px;border:0;border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,.1)"></iframe>`
    : '';

  return (
    <Dialog open={!!cfg} onOpenChange={o => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>嵌入代码 · {cfg?.name}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label className="text-xs">JS Widget（推荐：右下角浮动气泡）</Label>
            <div className="mt-1 flex gap-2">
              <pre className="flex-1 overflow-auto rounded-md bg-stone-900 p-3 font-mono text-xs text-emerald-300">
                {widget}
              </pre>
              <Button
                size="icon"
                variant="outline"
                onClick={() => {
                  navigator.clipboard.writeText(widget);
                  toast.success('已复制');
                }}
              >
                <Copy className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <div>
            <Label className="text-xs">iframe（嵌入到页面内某个区域）</Label>
            <div className="mt-1 flex gap-2">
              <pre className="flex-1 overflow-auto rounded-md bg-stone-900 p-3 font-mono text-xs text-emerald-300">
                {iframe}
              </pre>
              <Button
                size="icon"
                variant="outline"
                onClick={() => {
                  navigator.clipboard.writeText(iframe);
                  toast.success('已复制');
                }}
              >
                <Copy className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <p className="text-xs text-amber-700">
            ⚠️ 业务方网页的 Origin 必须在白名单内才能加载，否则 403。
          </p>
        </div>
        <DialogFooter>
          <Button onClick={onClose}>关闭</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

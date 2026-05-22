/** 嵌入式配置管理页 + 嵌入代码生成器 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Code2, Copy, Plus, Puzzle, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from '@/core/lib/toast';

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
import { Switch } from '@/core/components/ui/switch';
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
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { Textarea } from '@/core/components/ui/textarea';
import { agentApi } from '@/system/agents/services/agent';
import { appApi } from '@/system/apps/services/app';
import { embedConfigApi } from '@/system/embed_configs/services/embed';
import type { EmbedConfigItem } from '@/system/embed_configs/types/embed';

export const EmbedConfigsPage = () => {
  const { t } = useTranslation();
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
    mutationFn: (id: import('@/core/types/api').EntityId) => embedConfigApi.delete(id),
    onSuccess: () => {
      toast.success('已删除');
      qc.invalidateQueries({ queryKey: ['embed-configs'] });
      setDelCfg(null);
    },
  });

  const toggleMut = useMutation({
    mutationFn: (args: { id: import('@/core/types/api').EntityId; enabled: boolean }) =>
      embedConfigApi.update(args.id, { enabled: args.enabled }),
    onMutate: async args => {
      await qc.cancelQueries({ queryKey: ['embed-configs'] });
      const queries = qc.getQueriesData<{ items: EmbedConfigItem[]; total: number }>({
        queryKey: ['embed-configs'],
      });
      queries.forEach(([key, data]) => {
        if (!data) return;
        qc.setQueryData(key, {
          ...data,
          items: data.items.map(e =>
            e.id === args.id ? { ...e, enabled: args.enabled } : e,
          ),
        });
      });
      return { prev: queries };
    },
    onError: (_e, _v, ctx) => {
      ctx?.prev?.forEach(([key, data]) => qc.setQueryData(key, data));
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['embed-configs'] }),
  });

  const columns: DataTableColumn<EmbedConfigItem>[] = [
    {
      key: 'embed_key',
      header: t('table.embed_key'),
      width: 200,
      render: e => <span className="font-mono text-[11.5px] text-stone-700">{e.embed_key}</span>,
    },
    { key: 'name', header: t('common.name'), render: e => <span className="font-medium text-stone-900">{e.name}</span> },
    {
      key: 'allowed_origins',
      header: t('table.origins'),
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
          <Badge variant="warning">{t('common.not_configured')}</Badge>
        ),
    },
    {
      key: 'enabled',
      header: t('common.enabled'),
      width: 70,
      render: e => (
        <Switch
          checked={e.enabled}
          onCheckedChange={c => toggleMut.mutate({ id: e.id, enabled: c })}
        />
      ),
    },
    {
      key: 'actions',
      header: t('common.actions'),
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
          title={t('page.embed_configs_title')}
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
              icon={<Puzzle strokeWidth={1.5} />}
              title={t('empty.embed_configs')}
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

      <CreateEmbedModal
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

const CreateEmbedModal = ({
  open,
  onClose,
  onSubmit,
  loading,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (req: {
    name: string;
    agent_id: import('@/core/types/api').EntityId;
    app_id: import('@/core/types/api').EntityId;
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
    <Modal
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
      <ModalContent size="lg">
        <ModalHeader>
          <ModalTitle>新建嵌入配置</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
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
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button
            disabled={loading || !name || !agentId || !appId}
            onClick={() =>
              onSubmit({
                name,
                agent_id: agentId,
                app_id: appId,
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
        </ModalFooter>
      </ModalContent>
    </Modal>
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
          <CodeSnippet
            label="JS Widget"
            hint="推荐：右下角浮动气泡"
            code={widget}
          />
          <CodeSnippet
            label="iframe"
            hint="嵌入到页面内某个区域"
            code={iframe}
          />
          <p className="rounded-md border border-amber-200/70 bg-amber-50/60 px-3 py-2 text-[11.5px] text-amber-800">
            ⚠️ 业务方网页的 Origin 必须在白名单内才能加载，否则返回 403。
          </p>
        </div>
        <DialogFooter>
          <Button onClick={onClose}>关闭</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const CodeSnippet = ({
  label,
  hint,
  code,
}: {
  label: string;
  hint?: string;
  code: string;
}) => {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    toast.success('已复制');
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="overflow-hidden rounded-lg border border-stone-200/80 bg-warm-2/40">
      {/* 顶部条：标签 + 复制按钮，不与代码区重叠 */}
      <div className="flex items-center justify-between border-b border-stone-200/70 bg-white/40 px-3 py-1.5">
        <div className="flex items-baseline gap-2">
          <span className="text-[12px] font-medium text-stone-800">{label}</span>
          {hint && <span className="text-[11px] text-stone-500">· {hint}</span>}
        </div>
        <button
          type="button"
          onClick={onCopy}
          className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-stone-500 transition hover:bg-stone-100 hover:text-stone-900"
        >
          <Copy className="h-3 w-3" />
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <pre className="overflow-x-auto whitespace-pre-wrap break-all px-3.5 py-3 font-mono text-[12px] leading-relaxed text-stone-700">
        {code}
      </pre>
    </div>
  );
};

/** agents 管理页：启停 + 测试 invoke */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bot, Play, Plus, Trash2 } from 'lucide-react';

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
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import { Switch } from '@/core/components/ui/switch';
import { Textarea } from '@/core/components/ui/textarea';
import { useClientPagination } from '@/core/hooks/use-client-pagination';
import { useSmartNavigate } from '@/core/hooks/use-smart-navigate';
import { toast } from '@/core/lib/toast';
import { agentApi } from '@/system/agents/services/agent';
import type { AgentItem } from '@/system/agents/types/agent';

export const AgentsPage = () => {
  const { t } = useTranslation();
  const smartNav = useSmartNavigate();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [testAgent, setTestAgent] = useState<AgentItem | null>(null);
  const [delAgent, setDelAgent] = useState<AgentItem | null>(null);

  const listQ = useQuery({ queryKey: ['agents'], queryFn: () => agentApi.list() });
  const pg = useClientPagination(listQ.data ?? []);

  const toggleMut = useMutation({
    mutationFn: (args: { id: import('@/core/types/api').EntityId; enabled: boolean }) =>
      args.enabled ? agentApi.enable(args.id) : agentApi.disable(args.id),
    onMutate: async args => {
      await qc.cancelQueries({ queryKey: ['agents'] });
      const prev = qc.getQueryData<AgentItem[]>(['agents']);
      qc.setQueryData<AgentItem[]>(['agents'], old =>
        old?.map(a => (a.id === args.id ? { ...a, enabled: args.enabled } : a)),
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(['agents'], ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  });
  const createMut = useMutation({
    mutationFn: agentApi.create,
    onSuccess: () => {
      toast.success('Agent 已创建');
      qc.invalidateQueries({ queryKey: ['agents'] });
      setCreateOpen(false);
    },
  });
  const delMut = useMutation({
    mutationFn: (id: import('@/core/types/api').EntityId) => agentApi.delete(id),
    onSuccess: () => {
      toast.success('已删除');
      qc.invalidateQueries({ queryKey: ['agents'] });
      setDelAgent(null);
    },
  });

  const columns: DataTableColumn<AgentItem>[] = [
    {
      key: 'agent_key',
      header: t('table.agent_key'),
      width: 180,
      render: a => <span className="font-mono text-[11.5px] text-stone-700">{a.agent_key}</span>,
    },
    {
      key: 'name',
      header: t('common.name'),
      render: a => <span className="font-medium text-stone-900">{a.name}</span>,
    },
    {
      key: 'source',
      header: t('table.source'),
      width: 90,
      render: a =>
        a.source === 'graph' ? (
          <Badge variant="outline" className="bg-sky-50 text-sky-700">
            工作流
          </Badge>
        ) : (
          <Badge variant={a.source === 'local' ? 'primary' : 'outline'}>{a.source}</Badge>
        ),
    },
    {
      key: 'tags',
      header: t('table.tags'),
      render: a =>
        a.tags && a.tags.length ? (
          <div className="flex gap-1">
            {a.tags.map(t => (
              <Badge key={t} variant="outline">
                {t}
              </Badge>
            ))}
          </div>
        ) : (
          <span className="text-stone-400">—</span>
        ),
    },
    {
      key: 'enabled',
      header: t('common.enabled'),
      width: 70,
      render: a => (
        <span onClick={e => e.stopPropagation()}>
          <Switch
            checked={a.enabled}
            onCheckedChange={c => toggleMut.mutate({ id: a.id, enabled: c })}
          />
        </span>
      ),
    },
    {
      key: 'actions',
      header: t('common.actions'),
      align: 'right',
      width: 110,
      render: a => (
        <div className="inline-flex items-center gap-0.5">
          <button
            type="button"
            title={t('common.test')}
            className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-[11.5px] text-stone-600 hover:bg-stone-200 hover:text-stone-900"
            onClick={e => {
              e.stopPropagation();
              setTestAgent(a);
            }}
          >
            <Play className="h-3.5 w-3.5" /> {t('common.test')}
          </button>
          <button
            type="button"
            title="删除"
            className="rounded p-1 text-stone-600 hover:bg-red-100 hover:text-red-600 disabled:opacity-30 disabled:hover:bg-transparent"
            disabled={a.source === 'local'}
            onClick={e => {
              e.stopPropagation();
              setDelAgent(a);
            }}
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
          title={t('page.agents_title')}
          extra={
            <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> {t('common.create')}
            </Button>
          }
        />
        <DataTable
          columns={columns}
          rows={pg.rows}
          rowKey="id"
          loading={listQ.isLoading}
          onRowClick={a =>
            smartNav(`/agents/${a.id}`, {
              prefetch: () =>
                Promise.all([
                  qc.prefetchQuery({
                    queryKey: ['agent', a.id],
                    queryFn: () => agentApi.get(a.id),
                  }),
                  qc.prefetchQuery({
                    queryKey: ['agent-linked-kbs', a.id],
                    queryFn: () => agentApi.linkedKbs(a.id),
                  }),
                ]),
            })
          }
          emptyText={
            <EmptyState
              icon={<Bot strokeWidth={1.5} />}
              title={t('empty.agents')}
              action={
                <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
                  <Plus className="h-3.5 w-3.5" /> {t('common.create')}
                </Button>
              }
            />
          }
        />
        <TablePagination
          page={pg.page}
          pageSize={pg.pageSize}
          total={pg.total}
          onPageChange={pg.setPage}
          onPageSizeChange={pg.setPageSize}
        />
      </SectionCard>

      <CreateAgentModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={createMut.mutate}
        loading={createMut.isPending}
      />
      <TestAgentSheet agent={testAgent} onClose={() => setTestAgent(null)} />
      <ConfirmDialog
        open={!!delAgent}
        title="删除外部 agent"
        description={`确认删除 ${delAgent?.agent_key}？本地 agent 仅能 disable。`}
        variant="danger"
        confirmText="删除"
        onConfirm={() => delAgent && delMut.mutate(delAgent.id)}
        onCancel={() => setDelAgent(null)}
      />
    </div>
  );
};

const CreateAgentModal = ({
  open,
  onClose,
  onSubmit,
  loading,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (req: {
    agent_key: string;
    name: string;
    source: 'dify' | 'fastgpt' | 'coze';
    config?: Record<string, unknown>;
  }) => void;
  loading: boolean;
}) => {
  const [key, setKey] = useState('');
  const [name, setName] = useState('');
  const [source, setSource] = useState<'dify' | 'fastgpt' | 'coze'>('dify');
  const [configRaw, setConfigRaw] = useState(
    '{\n  "endpoint": "https://...",\n  "api_key_env": "..."\n}',
  );

  const submit = () => {
    let config: Record<string, unknown> | undefined;
    try {
      config = configRaw.trim() ? JSON.parse(configRaw) : undefined;
    } catch {
      toast.error('config 不是合法 JSON');
      return;
    }
    onSubmit({ agent_key: key, name, source, config });
  };

  return (
    <Modal
      open={open}
      onOpenChange={o => {
        if (!o) {
          setKey('');
          setName('');
          setSource('dify');
          onClose();
        }
      }}
    >
      <ModalContent size="md">
        <ModalHeader>
          <ModalTitle>新建外部 Agent</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div className="space-y-1.5">
            <Label>agent_key</Label>
            <Input value={key} onChange={e => setKey(e.target.value)} placeholder="customer-faq" />
          </div>
          <div className="space-y-1.5">
            <Label>名称</Label>
            <Input value={name} onChange={e => setName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>来源</Label>
            <Select value={source} onValueChange={v => setSource(v as typeof source)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="dify">dify</SelectItem>
                <SelectItem value="fastgpt">fastgpt</SelectItem>
                <SelectItem value="coze">coze</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>config（JSON）</Label>
            <Textarea
              className="font-mono text-xs"
              rows={8}
              value={configRaw}
              onChange={e => setConfigRaw(e.target.value)}
            />
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button disabled={loading || !key || !name} onClick={submit}>
            {loading ? '创建中...' : '创建'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

const TestAgentSheet = ({ agent, onClose }: { agent: AgentItem | null; onClose: () => void }) => {
  const [input, setInput] = useState('hi');
  const [result, setResult] = useState<string>('');
  const mut = useMutation({
    mutationFn: () => agentApi.test(agent!.id, input),
    onSuccess: r => setResult(r.answer),
    onError: () => setResult(''),
  });

  return (
    <Sheet
      open={!!agent}
      onOpenChange={o => {
        if (!o) {
          setInput('hi');
          setResult('');
          onClose();
        }
      }}
    >
      <SheetContent width="w-[560px]">
        <SheetHeader>
          <SheetTitle>测试 · {agent?.agent_key}</SheetTitle>
        </SheetHeader>
        <SheetBody className="space-y-4">
          <div className="space-y-1.5">
            <Label>输入</Label>
            <Textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              rows={4}
              placeholder="hi"
            />
          </div>
          <Button onClick={() => mut.mutate()} disabled={mut.isPending}>
            {mut.isPending ? '调用中...' : '发送'}
          </Button>
          {result && (
            <div>
              <Label>回复</Label>
              <div className="mt-1 rounded-md border border-stone-200 bg-stone-50 p-3 text-sm whitespace-pre-wrap">
                {result}
              </div>
            </div>
          )}
        </SheetBody>
        <SheetFooter>
          <Button variant="ghost" onClick={onClose}>
            关闭
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
};

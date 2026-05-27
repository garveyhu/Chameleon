/** 应用目录页：统一展示可被调用的 AI 能力（代码 / 对话编排 / 流程编排 / 外部）
 *
 * - kind 徽标 + kind 筛选 tab
 * - 行为按 kind 分流：source=graph → graph 编辑器；其余 → agent 详情页
 * - 新建应用：编排方式选择器（对话编排 / 流程编排 → 建 graph 跳编辑器；代码应用 → 指引弹窗）
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Boxes, Code2, MessageSquare, Play, Plus, Trash2, Workflow } from 'lucide-react';

import { OrchestrationBadge } from '@/core/components/common/orchestration-badge';
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
import { cn } from '@/core/lib/cn';
import { resolveOrchestrationKind } from '@/core/lib/orchestration';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { agentApi } from '@/system/agents/services/agent';
import type { AgentItem } from '@/system/agents/types/agent';
import { graphApi } from '@/system/graphs/services/graph';
import type { GraphKind, GraphSpec } from '@/system/graphs/types/graph';

// ── 新建工作流初始 spec（复用 graphs-page 同款，避免重造）─────────
/** 流程型：空管线（start → end），自己往里拖节点 */
const WORKFLOW_SPEC: GraphSpec = {
  nodes: [
    { id: 'start', type: 'start', name: 'Start', position: { x: 80, y: 200 } },
    { id: 'end', type: 'end', name: 'End', position: { x: 480, y: 200 } },
  ],
  edges: [{ id: 'e_start_end', source: 'start', target: 'end' }],
};

/** 对话型：开箱即聊（start → LLM → end），建完即可对话调试 */
const CHATFLOW_SPEC: GraphSpec = {
  nodes: [
    {
      id: 'start',
      type: 'start',
      name: 'Start',
      position: { x: 80, y: 200 },
      data: { opener: '你好！我是你的智能助理，有什么可以帮你？' },
    },
    {
      id: 'llm',
      type: 'llm',
      name: '对话',
      position: { x: 340, y: 200 },
      data: { system_prompt: '你是一个有帮助的中文助理，回答简洁、友好。' },
    },
    { id: 'end', type: 'end', name: 'End', position: { x: 600, y: 200 } },
  ],
  edges: [
    { id: 'e_start_llm', source: 'start', target: 'llm' },
    { id: 'e_llm_end', source: 'llm', target: 'end' },
  ],
};

// ── kind 筛选 ──────────────────────────────────────────────
type KindFilter = 'all' | 'code' | 'chatflow' | 'workflow' | 'external';

const KIND_FILTERS: { key: KindFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'code', label: '代码' },
  { key: 'chatflow', label: '对话编排' },
  { key: 'workflow', label: '流程编排' },
  { key: 'external', label: '外部' },
];

export const AgentsPage = () => {
  const { t } = useTranslation();
  const smartNav = useSmartNavigate();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [testAgent, setTestAgent] = useState<AgentItem | null>(null);
  const [delAgent, setDelAgent] = useState<AgentItem | null>(null);
  const [kindFilter, setKindFilter] = useState<KindFilter>('all');

  const listQ = useQuery({ queryKey: ['agents'], queryFn: () => agentApi.list() });
  const rows = useMemo(() => listQ.data ?? [], [listQ.data]);

  const counts = useMemo(() => {
    const acc: Record<KindFilter, number> = {
      all: rows.length,
      code: 0,
      chatflow: 0,
      workflow: 0,
      external: 0,
    };
    for (const a of rows) {
      const k = resolveOrchestrationKind(a.source, a.graph_kind);
      if (k) acc[k] += 1;
    }
    return acc;
  }, [rows]);

  const filtered = useMemo(
    () =>
      kindFilter === 'all'
        ? rows
        : rows.filter(a => resolveOrchestrationKind(a.source, a.graph_kind) === kindFilter),
    [rows, kindFilter],
  );
  const pg = useClientPagination(filtered);

  const toggleMut = useMutation({
    mutationFn: (args: { id: EntityId; enabled: boolean }) =>
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
  const delMut = useMutation({
    mutationFn: (id: EntityId) => agentApi.delete(id),
    onSuccess: () => {
      toast.success('已删除');
      qc.invalidateQueries({ queryKey: ['agents'] });
      setDelAgent(null);
    },
  });

  /** source=graph 的应用主操作 = 编辑（跳 graph 编辑器）；其余 = 详情页 */
  const openApp = (a: AgentItem) => {
    if (a.source === 'graph' && a.graph_id != null) {
      nav(`/graphs/${a.graph_id}/edit`);
      return;
    }
    smartNav(`/agents/${a.id}`, {
      prefetch: () =>
        Promise.all([
          qc.prefetchQuery({ queryKey: ['agent', a.id], queryFn: () => agentApi.get(a.id) }),
          qc.prefetchQuery({
            queryKey: ['agent-linked-kbs', a.id],
            queryFn: () => agentApi.linkedKbs(a.id),
          }),
        ]),
    });
  };

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
      key: 'kind',
      header: t('table.orchestration', '编排方式'),
      width: 96,
      render: a => <OrchestrationBadge source={a.source} graphKind={a.graph_kind} />,
    },
    {
      key: 'tags',
      header: t('table.tags'),
      render: a =>
        a.tags && a.tags.length ? (
          <div className="flex gap-1">
            {a.tags.map(tag => (
              <Badge key={tag} variant="outline">
                {tag}
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
              <Plus className="h-3.5 w-3.5" /> {t('agents.create_app', '新建应用')}
            </Button>
          }
        />

        <div className="mb-2 flex items-center gap-1">
          {KIND_FILTERS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => setKindFilter(key)}
              className={cn(
                'rounded-md px-2.5 py-1 text-[11.5px] transition',
                kindFilter === key
                  ? 'bg-stone-900 text-white'
                  : 'text-stone-500 hover:bg-stone-100 hover:text-stone-700',
              )}
            >
              {label}
              <span
                className={cn(
                  'ml-1 text-[10px]',
                  kindFilter === key ? 'text-stone-300' : 'text-stone-400',
                )}
              >
                {counts[key]}
              </span>
            </button>
          ))}
        </div>

        <DataTable
          columns={columns}
          rows={pg.rows}
          rowKey="id"
          loading={listQ.isLoading}
          onRowClick={openApp}
          emptyText={
            <EmptyState
              icon={<Boxes strokeWidth={1.5} />}
              title={t('empty.agents')}
              action={
                <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
                  <Plus className="h-3.5 w-3.5" /> {t('agents.create_app', '新建应用')}
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

      <CreateAppModal open={createOpen} onClose={() => setCreateOpen(false)} />
      <TestAgentSheet agent={testAgent} onClose={() => setTestAgent(null)} />
      <ConfirmDialog
        open={!!delAgent}
        title="删除外部应用"
        description={`确认删除 ${delAgent?.agent_key}？代码应用仅能 disable。`}
        variant="danger"
        confirmText="删除"
        onConfirm={() => delAgent && delMut.mutate(delAgent.id)}
        onCancel={() => setDelAgent(null)}
      />
    </div>
  );
};

// ── 新建应用：编排方式选择器 ────────────────────────────────
type AppMethod = 'chatflow' | 'workflow' | 'code';

const METHOD_META: Record<
  AppMethod,
  { label: string; desc: string; icon: typeof MessageSquare }
> = {
  chatflow: {
    label: '对话编排',
    desc: '聊天 I/O + 开场白 + 对话调试，可发布为可对话应用',
    icon: MessageSquare,
  },
  workflow: {
    label: '流程编排',
    desc: '一次性管线：填输入跑、批处理；可视化拖拽节点',
    icon: Workflow,
  },
  code: {
    label: '代码应用',
    desc: '用 @agent 装饰器在代码里定义；提交进 agents 目录自动注册',
    icon: Code2,
  },
};

const CreateAppModal = ({ open, onClose }: { open: boolean; onClose: () => void }) => {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [method, setMethod] = useState<AppMethod>('chatflow');
  const [graphKey, setGraphKey] = useState('');
  const [graphName, setGraphName] = useState('');

  const reset = () => {
    setMethod('chatflow');
    setGraphKey('');
    setGraphName('');
  };

  const createMut = useMutation({
    mutationFn: (kind: GraphKind) =>
      graphApi.create({
        graph_key: graphKey.trim(),
        name: graphName.trim() || graphKey.trim(),
        kind,
        spec: kind === 'chatflow' ? CHATFLOW_SPEC : WORKFLOW_SPEC,
      }),
    onSuccess: g => {
      toast.success('已创建');
      qc.invalidateQueries({ queryKey: ['graphs'] });
      onClose();
      reset();
      nav(`/graphs/${g.id}/edit`);
    },
  });

  const isGraphMethod = method === 'chatflow' || method === 'workflow';

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
          <ModalTitle>新建应用</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-3">
          <div>
            <label className="mb-1.5 block text-[12px] text-stone-600">编排方式</label>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {(['chatflow', 'workflow', 'code'] as const).map(m => {
                const meta = METHOD_META[m];
                const Icon = meta.icon;
                const active = method === m;
                return (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setMethod(m)}
                    className={cn(
                      'rounded-lg border p-2.5 text-left transition',
                      active
                        ? 'border-stone-900 bg-stone-50 ring-1 ring-stone-900'
                        : 'border-stone-200 hover:border-stone-300 hover:bg-stone-50',
                    )}
                  >
                    <div className="flex items-center gap-1.5 text-[12.5px] font-medium text-stone-900">
                      <Icon className="h-3.5 w-3.5" />
                      {meta.label}
                    </div>
                    <div className="mt-1 text-[10.5px] leading-snug text-stone-500">
                      {meta.desc}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {isGraphMethod ? (
            <>
              <div>
                <label className="mb-1 block text-[12px] text-stone-600">
                  应用标识
                  <span className="ml-1 text-stone-400">（唯一；a-zA-Z0-9_-）</span>
                </label>
                <Input
                  value={graphKey}
                  onChange={e => setGraphKey(e.target.value)}
                  placeholder="my-app"
                  className="h-8 font-mono"
                />
              </div>
              <div>
                <label className="mb-1 block text-[12px] text-stone-600">显示名</label>
                <Input
                  value={graphName}
                  onChange={e => setGraphName(e.target.value)}
                  placeholder="留空时与应用标识一致"
                  className="h-8"
                />
              </div>
            </>
          ) : (
            <div className="rounded-lg border border-stone-200 bg-stone-50 p-3 text-[12px] leading-relaxed text-stone-600">
              <p className="font-medium text-stone-800">代码应用不在 Web 端创建</p>
              <p className="mt-1.5">
                用 <code className="rounded bg-stone-200 px-1 py-0.5 font-mono text-[11px]">@agent</code>{' '}
                装饰器定义你的智能体，把文件提交进项目的{' '}
                <code className="rounded bg-stone-200 px-1 py-0.5 font-mono text-[11px]">agents/</code>{' '}
                目录，平台会在加载时自动扫描入表，随后即可在本目录看到并配置。
              </p>
            </div>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          {isGraphMethod ? (
            <Button
              onClick={() => createMut.mutate(method)}
              disabled={!graphKey.trim() || createMut.isPending}
            >
              {createMut.isPending ? '创建中…' : '创建并编辑'}
            </Button>
          ) : (
            <Button onClick={onClose}>知道了</Button>
          )}
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

/** agents 管理页：启停 + 测试 invoke */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Play, Plus, Trash2 } from 'lucide-react';
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
import { Switch } from '@/core/components/ui/switch';
import { Textarea } from '@/core/components/ui/textarea';
import { agentApi } from '@/system/agents/services/agent';
import type { AgentItem } from '@/system/agents/types/agent';

export const AgentsPage = () => {
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [testAgent, setTestAgent] = useState<AgentItem | null>(null);
  const [delAgent, setDelAgent] = useState<AgentItem | null>(null);

  const listQ = useQuery({ queryKey: ['agents'], queryFn: () => agentApi.list() });

  const enableMut = useMutation({
    mutationFn: (id: number) => agentApi.enable(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  });
  const disableMut = useMutation({
    mutationFn: (id: number) => agentApi.disable(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
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
    mutationFn: (id: number) => agentApi.delete(id),
    onSuccess: () => {
      toast.success('已删除');
      qc.invalidateQueries({ queryKey: ['agents'] });
      setDelAgent(null);
    },
  });

  const columns: DataTableColumn<AgentItem>[] = [
    {
      key: 'agent_key',
      header: 'agent_key',
      width: 180,
      render: a => <span className="font-mono text-[11.5px] text-stone-700">{a.agent_key}</span>,
    },
    { key: 'name', header: '名称', render: a => <span className="font-medium text-stone-900">{a.name}</span> },
    {
      key: 'source',
      header: '来源',
      width: 90,
      render: a => (
        <Badge variant={a.source === 'local' ? 'primary' : 'outline'}>{a.source}</Badge>
      ),
    },
    {
      key: 'tags',
      header: '标签',
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
      header: '启用',
      width: 70,
      render: a => (
        <Switch
          checked={a.enabled}
          onCheckedChange={c => (c ? enableMut.mutate(a.id) : disableMut.mutate(a.id))}
        />
      ),
    },
    {
      key: 'actions',
      header: '操作',
      align: 'right',
      width: 110,
      render: a => (
        <div className="inline-flex items-center gap-0.5">
          <button
            type="button"
            title="测试"
            className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-[11.5px] text-stone-600 hover:bg-stone-200 hover:text-stone-900"
            onClick={() => setTestAgent(a)}
          >
            <Play className="h-3.5 w-3.5" /> 测试
          </button>
          <button
            type="button"
            title="删除"
            className="rounded p-1 text-stone-600 hover:bg-red-100 hover:text-red-600 disabled:opacity-30 disabled:hover:bg-transparent"
            disabled={a.source === 'local'}
            onClick={() => setDelAgent(a)}
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
          title="智能体"
          extra={
            <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> 新建外部
            </Button>
          }
        />
        <DataTable columns={columns} rows={listQ.data || []} rowKey="id" loading={listQ.isLoading} emptyText="还没有智能体" />
      </SectionCard>

      <CreateAgentSheet
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

const CreateAgentSheet = ({
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
  const [configRaw, setConfigRaw] = useState('{\n  "endpoint": "https://...",\n  "api_key_env": "..."\n}');

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
    <Sheet
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
      <SheetContent>
        <SheetHeader>
          <SheetTitle>新建外部 Agent</SheetTitle>
        </SheetHeader>
        <SheetBody className="space-y-4">
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
        </SheetBody>
        <SheetFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button disabled={loading || !key || !name} onClick={submit}>
            {loading ? '创建中...' : '创建'}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
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

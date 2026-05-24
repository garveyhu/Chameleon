/** 工作流列表页 —— 简版列表 + 新建 + 跳转编辑 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Rocket, Sparkles, Trash2, Workflow } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { DataTable, SectionCard } from '@/core/components/table';
import type { DataTableColumn } from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { StatusBadge } from '@/core/components/ui/status-badge';
import { Textarea } from '@/core/components/ui/textarea';
import { confirm } from '@/core/lib/confirm';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import { graphApi } from '@/system/graphs/services/graph';
import type { GraphItem, GraphSpec } from '@/system/graphs/types/graph';

const DEFAULT_SPEC: GraphSpec = {
  nodes: [
    {
      id: 'start',
      type: 'start',
      name: 'Start',
      position: { x: 80, y: 200 },
    },
    {
      id: 'end',
      type: 'end',
      name: 'End',
      position: { x: 480, y: 200 },
    },
  ],
  edges: [{ id: 'e_start_end', source: 'start', target: 'end' }],
};

export const GraphsPage = () => {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [graphKey, setGraphKey] = useState('');
  const [graphName, setGraphName] = useState('');
  const [genOpen, setGenOpen] = useState(false);
  const [genDesc, setGenDesc] = useState('');
  const [genKey, setGenKey] = useState('');

  const listQ = useQuery({
    queryKey: ['graphs'],
    queryFn: () => graphApi.list(),
  });

  const genMut = useMutation({
    mutationFn: () =>
      graphApi.generate({
        description: genDesc.trim(),
        graph_key: genKey.trim(),
        name: genKey.trim(),
      }),
    onSuccess: g => {
      toast.success('AI 已生成工作流');
      qc.invalidateQueries({ queryKey: ['graphs'] });
      setGenOpen(false);
      setGenDesc('');
      setGenKey('');
      nav(`/graphs/${g.id}/edit`);
    },
    onError: e => toast.error(`生成失败：${(e as Error).message}`),
  });

  const createMut = useMutation({
    mutationFn: () =>
      graphApi.create({
        graph_key: graphKey.trim(),
        name: graphName.trim() || graphKey.trim(),
        spec: DEFAULT_SPEC,
      }),
    onSuccess: g => {
      toast.success('已创建');
      qc.invalidateQueries({ queryKey: ['graphs'] });
      setCreateOpen(false);
      setGraphKey('');
      setGraphName('');
      nav(`/graphs/${g.id}/edit`);
    },
  });

  const delMut = useMutation({
    mutationFn: (id: string | number) => graphApi.delete(id),
    onSuccess: () => {
      toast.success('已删除');
      qc.invalidateQueries({ queryKey: ['graphs'] });
    },
  });

  const onDelete = async (g: GraphItem) => {
    if (
      await confirm({
        title: '确认删除？',
        description: `工作流 ${g.graph_key} 将被软删；历史 graph_runs 仍保留。`,
        danger: true,
      })
    ) {
      delMut.mutate(g.id);
    }
  };

  const columns: DataTableColumn<GraphItem>[] = [
    {
      key: 'identity',
      header: '工作流',
      render: g => (
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-stone-100 text-stone-500">
            <Workflow className="h-3.5 w-3.5" />
          </span>
          <div className="min-w-0">
            <div className="truncate text-[12.5px] font-medium text-stone-900">
              {g.name}
            </div>
            <div className="truncate font-mono text-[10.5px] text-stone-400">
              {g.graph_key}
            </div>
          </div>
        </div>
      ),
    },
    {
      key: 'status',
      header: '状态',
      width: 96,
      render: g => (
        <StatusBadge tone={g.enabled ? 'success' : 'neutral'}>
          {g.enabled ? '启用' : '禁用'}
        </StatusBadge>
      ),
    },
    {
      key: 'published',
      header: '发布',
      width: 110,
      render: g =>
        g.published_version && g.published_version > 0 ? (
          <span
            className="inline-flex items-center gap-1 rounded bg-emerald-50 px-1.5 py-0.5 text-[10.5px] text-emerald-700"
            title={
              g.published_at
                ? `最近发布: ${formatDateTime(g.published_at)}`
                : ''
            }
          >
            <Rocket className="h-3 w-3" /> v{g.published_version}
          </span>
        ) : (
          <span className="text-[10.5px] text-amber-600">草稿</span>
        ),
    },
    {
      key: 'created_at',
      header: '创建时间',
      width: 168,
      render: g => (
        <span className="font-mono text-[11px] text-stone-500">
          {formatDateTime(g.created_at)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      width: 56,
      align: 'right',
      render: g => (
        <button
          type="button"
          title="删除"
          onClick={e => {
            e.stopPropagation();
            void onDelete(g);
          }}
          className="rounded p-1 text-stone-400 opacity-0 transition hover:bg-rose-50 hover:text-rose-600 group-hover:opacity-100"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      ),
    },
  ];

  return (
    <SectionCard>
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="flex items-center gap-1.5 text-[14px] font-medium text-stone-900">
            <Workflow className="h-4 w-4 text-stone-500" />
            工作流
          </h2>
          <p className="mt-0.5 text-[11.5px] text-stone-500">
            可视化编排：节点 = LLM / KB / Tool / 条件 / End；
            拖连线组装能力，跑出来可在 trace tree 看嵌套结构
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setGenOpen(true)}
            title="用自然语言描述，AI 自动生成工作流图"
          >
            <Sparkles className="mr-1 h-3 w-3" />
            AI 生成
          </Button>
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="mr-1 h-3 w-3" />
            新建工作流
          </Button>
        </div>
      </header>

      <DataTable
        columns={columns}
        rows={listQ.data ?? []}
        rowKey={g => String(g.id)}
        loading={listQ.isLoading}
        leftBar={g => (g.enabled ? 'bg-emerald-400' : 'bg-stone-300')}
        onRowClick={g => nav(`/graphs/${g.id}/edit`)}
        emptyText='还没有工作流；点右上"新建"开始'
      />

      <Modal open={createOpen} onOpenChange={o => !o && setCreateOpen(false)}>
        <ModalContent size="md">
          <ModalHeader>
            <ModalTitle>新建工作流</ModalTitle>
          </ModalHeader>
          <ModalBody className="space-y-3">
            <div>
              <label className="mb-1 block text-[12px] text-stone-600">
                graph_key
                <span className="ml-1 text-stone-400">
                  （唯一；可用 a-zA-Z0-9_-）
                </span>
              </label>
              <Input
                value={graphKey}
                onChange={e => setGraphKey(e.target.value)}
                placeholder="my-workflow"
                className="h-8 font-mono"
              />
            </div>
            <div>
              <label className="mb-1 block text-[12px] text-stone-600">
                显示名
              </label>
              <Input
                value={graphName}
                onChange={e => setGraphName(e.target.value)}
                placeholder="留空时与 graph_key 一致"
                className="h-8"
              />
            </div>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" onClick={() => setCreateOpen(false)}>
              取消
            </Button>
            <Button
              onClick={() => createMut.mutate()}
              disabled={!graphKey.trim() || createMut.isPending}
            >
              创建并编辑
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      <Modal open={genOpen} onOpenChange={o => !o && setGenOpen(false)}>
        <ModalContent size="md">
          <ModalHeader>
            <ModalTitle>AI 生成工作流</ModalTitle>
          </ModalHeader>
          <ModalBody className="space-y-3">
            <div>
              <label className="mb-1 block text-[12px] text-stone-600">
                描述你要的智能体（自然语言）
              </label>
              <Textarea
                value={genDesc}
                onChange={e => setGenDesc(e.target.value)}
                rows={4}
                placeholder="例：做一个客服助理，先查 smoke 知识库，再结合资料和对话历史回答用户。"
                className="text-[12.5px]"
              />
            </div>
            <div>
              <label className="mb-1 block text-[12px] text-stone-600">
                graph_key
                <span className="ml-1 text-stone-400">（唯一；a-zA-Z0-9_-）</span>
              </label>
              <Input
                value={genKey}
                onChange={e => setGenKey(e.target.value)}
                placeholder="ai-customer-bot"
                className="h-8 font-mono"
              />
            </div>
            <p className="text-[10.5px] leading-snug text-stone-400">
              AI 会据描述生成节点 + 连线，落到画布；可在编辑器里继续微调、对话调试。
            </p>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" onClick={() => setGenOpen(false)}>
              取消
            </Button>
            <Button
              onClick={() => genMut.mutate()}
              disabled={
                genDesc.trim().length < 4 ||
                !genKey.trim() ||
                genMut.isPending
              }
            >
              {genMut.isPending ? '生成中…' : '生成并编辑'}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </SectionCard>
  );
};

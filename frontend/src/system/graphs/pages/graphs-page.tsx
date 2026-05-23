/** 工作流列表页 —— 简版列表 + 新建 + 跳转编辑 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2, Workflow } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { SectionCard } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
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
import { cn } from '@/core/lib/cn';
import { confirm } from '@/core/lib/confirm';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import { graphApi } from '@/system/graphs/services/graph';
import type { GraphSpec } from '@/system/graphs/types/graph';

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

  const listQ = useQuery({
    queryKey: ['graphs'],
    queryFn: () => graphApi.list(),
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
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1 h-3 w-3" />
          新建工作流
        </Button>
      </header>

      {listQ.isLoading ? (
        <div className="py-12 text-center text-[12px] text-stone-400">加载中…</div>
      ) : !listQ.data?.length ? (
        <div className="py-12 text-center text-[12px] text-stone-400">
          还没有工作流；点右上"新建"开始
        </div>
      ) : (
        <table className="w-full text-[12.5px]">
          <thead className="text-[11px] uppercase tracking-wider text-stone-500">
            <tr>
              <th className="px-2 py-2 text-left">graph_key</th>
              <th className="px-2 py-2 text-left">名称</th>
              <th className="px-2 py-2 text-left">状态</th>
              <th className="px-2 py-2 text-left">创建时间</th>
              <th className="px-2 py-2 text-right" />
            </tr>
          </thead>
          <tbody>
            {listQ.data.map(g => (
              <tr
                key={g.id}
                className={cn(
                  'cursor-pointer border-t border-stone-200/70 hover:bg-stone-50',
                )}
                onClick={() => nav(`/graphs/${g.id}/edit`)}
              >
                <td className="px-2 py-2 font-mono text-[11.5px]">
                  {g.graph_key}
                </td>
                <td className="px-2 py-2 text-stone-800">{g.name}</td>
                <td className="px-2 py-2">
                  <Badge
                    variant="outline"
                    className={cn(
                      'text-[10.5px]',
                      g.enabled
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-stone-50 text-stone-500',
                    )}
                  >
                    {g.enabled ? '启用' : '禁用'}
                  </Badge>
                </td>
                <td className="px-2 py-2 font-mono text-[11px] text-stone-500">
                  {formatDateTime(g.created_at)}
                </td>
                <td className="px-2 py-2 text-right">
                  <button
                    type="button"
                    title="删除"
                    onClick={async e => {
                      e.stopPropagation();
                      if (
                        await confirm({
                          title: '确认删除？',
                          description: `工作流 ${g.graph_key} 将被软删；历史 graph_runs 仍保留。`,
                        })
                      ) {
                        delMut.mutate(g.id);
                      }
                    }}
                    className="rounded p-1 text-stone-400 hover:bg-rose-50 hover:text-rose-600"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

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
    </SectionCard>
  );
};

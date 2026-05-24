/** Datasets 列表页 —— 列表 + 新建 + 删除（P21.1 PR #61） */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Database, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { SectionCard } from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import {
  Modal,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { confirm } from '@/core/lib/confirm';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { datasetApi } from '@/system/datasets/services/dataset';
import type {
  CreateDatasetRequest,
  DatasetItem,
} from '@/system/datasets/types/dataset';

export const DatasetsPage = () => {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);

  const listQ = useQuery({
    queryKey: ['datasets'],
    queryFn: () => datasetApi.list(),
  });

  const deleteMut = useMutation({
    mutationFn: (id: EntityId) => datasetApi.delete(id),
    onSuccess: () => {
      toast.success('已删除');
      qc.invalidateQueries({ queryKey: ['datasets'] });
    },
  });

  const handleDelete = async (ds: DatasetItem) => {
    const ok = await confirm({
      title: `删除 dataset "${ds.name}"？`,
      description: `共 ${ds.item_count} 条 items；删除后所有 dataset_runs 关联失效（CASCADE）。不可恢复。`,
      confirmText: '删除',
      danger: true,
    });
    if (!ok) return;
    deleteMut.mutate(ds.id);
  };

  return (
    <div className="space-y-3">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-stone-500" />
          <h1 className="text-[15px] font-medium text-stone-800">
            Datasets
          </h1>
          <span className="text-[11px] text-stone-400">
            {listQ.data?.length ?? '...'} 个
          </span>
        </div>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1 h-3.5 w-3.5" /> 新建 Dataset
        </Button>
      </header>

      <SectionCard className="!p-0">
        <table className="w-full text-[12.5px]">
          <thead className="bg-warm-2/40 text-[11px] text-stone-500">
            <tr>
              <th className="px-3 py-2 text-left">名称</th>
              <th className="px-3 py-2 text-left">描述</th>
              <th className="px-3 py-2 text-right">items</th>
              <th className="px-3 py-2 text-right">创建</th>
              <th className="px-3 py-2 text-right">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {(listQ.data ?? []).map(ds => (
              <tr
                key={String(ds.id)}
                className="cursor-pointer hover:bg-warm-2/30"
                onClick={() => nav(`/datasets/${ds.id}`)}
              >
                <td className="px-3 py-2 font-medium text-stone-800">
                  {ds.name}
                </td>
                <td className="px-3 py-2 text-stone-500">
                  {ds.description ?? '—'}
                </td>
                <td
                  className={cn(
                    'px-3 py-2 text-right font-mono tnum',
                    ds.item_count > 0 ? 'text-stone-700' : 'text-stone-400',
                  )}
                >
                  {ds.item_count}
                </td>
                <td className="px-3 py-2 text-right text-[11.5px] text-stone-500">
                  {formatDateTime(ds.created_at)}
                </td>
                <td className="px-3 py-2 text-right">
                  <button
                    type="button"
                    onClick={e => {
                      e.stopPropagation();
                      handleDelete(ds);
                    }}
                    className="rounded p-1 text-stone-400 hover:bg-rose-50 hover:text-rose-600"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </td>
              </tr>
            ))}
            {listQ.data?.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="px-3 py-12 text-center text-[12px] text-stone-400"
                >
                  暂无 dataset，点右上「新建」开始
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </SectionCard>

      {createOpen && (
        <CreateModal
          onClose={() => setCreateOpen(false)}
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ['datasets'] });
            setCreateOpen(false);
          }}
        />
      )}
    </div>
  );
};

interface CreateModalProps {
  onClose: () => void;
  onCreated: () => void;
}

const CreateModal = ({ onClose, onCreated }: CreateModalProps) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  const createMut = useMutation({
    mutationFn: (p: CreateDatasetRequest) => datasetApi.create(p),
    onSuccess: () => {
      toast.success('已创建');
      onCreated();
    },
  });

  return (
    <Modal open onOpenChange={open => !open && onClose()}>
      <ModalContent>
        <ModalHeader>
          <ModalTitle>新建 Dataset</ModalTitle>
        </ModalHeader>
        <div className="space-y-3 px-4 py-3">
          <div>
            <label className="mb-1 block text-[11.5px] text-stone-600">
              名称
            </label>
            <Input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="例如 RAG 基线测试"
              className="text-[12.5px]"
            />
          </div>
          <div>
            <label className="mb-1 block text-[11.5px] text-stone-600">
              描述（可选）
            </label>
            <Textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              rows={3}
              className="text-[12.5px]"
            />
          </div>
        </div>
        <ModalFooter>
          <Button variant="ghost" size="sm" onClick={onClose}>
            取消
          </Button>
          <Button
            size="sm"
            disabled={!name.trim() || createMut.isPending}
            onClick={() =>
              createMut.mutate({
                name: name.trim(),
                description: description.trim() || undefined,
              })
            }
          >
            创建
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

/** 数据集列表页 —— DataTable + 新建 + 删除 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Database, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { DataTable, type DataTableColumn } from '@/core/components/table';
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
  const [sortKey, setSortKey] = useState('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

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
      title: `删除数据集「${ds.name}」？`,
      description: `共 ${ds.item_count} 条样本；删除后该数据集的全部样本与历史运行记录一并清除，不可恢复。`,
      confirmText: '删除',
      danger: true,
    });
    if (!ok) return;
    deleteMut.mutate(ds.id);
  };

  const cols: DataTableColumn<DatasetItem>[] = [
    {
      key: 'name',
      header: '名称',
      render: r => (
        <div className="min-w-0">
          <div className="truncate font-medium text-stone-800">{r.name}</div>
          {r.description && (
            <div className="truncate text-[11px] text-stone-400">
              {r.description}
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'item_count',
      header: '样本数',
      align: 'right',
      width: 92,
      sortable: true,
      render: r => (
        <span
          className={cn(
            'tnum',
            r.item_count > 0 ? 'text-stone-700' : 'text-stone-400',
          )}
        >
          {r.item_count}
        </span>
      ),
    },
    {
      key: 'created_at',
      header: '创建时间',
      align: 'right',
      width: 168,
      render: r => (
        <span className="text-[11.5px] text-stone-500">
          {formatDateTime(r.created_at)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      width: 56,
      render: r => (
        <button
          type="button"
          onClick={e => {
            e.stopPropagation();
            handleDelete(r);
          }}
          className="rounded p-1 text-stone-400 hover:bg-rose-50 hover:text-rose-600"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      ),
    },
  ];

  const rows = [...(listQ.data ?? [])].sort((a, b) => {
    if (sortKey === 'item_count') {
      return sortOrder === 'asc'
        ? a.item_count - b.item_count
        : b.item_count - a.item_count;
    }
    return 0;
  });

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-stone-500" />
          <h1 className="text-[14px] font-medium text-stone-800">数据集</h1>
          <span className="text-[11px] text-stone-400">
            {listQ.data?.length ?? '…'} 个
          </span>
        </div>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1 h-3.5 w-3.5" /> 新建数据集
        </Button>
      </div>

      <DataTable
        columns={cols}
        rows={rows}
        rowKey="id"
        sortKey={sortKey}
        sortOrder={sortOrder}
        onSortChange={(k, o) => {
          setSortKey(k);
          setSortOrder(o);
        }}
        loading={listQ.isLoading}
        onRowClick={r => nav(`/datasets/${r.id}`)}
        emptyText="暂无数据集"
        emptyExtra={
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setCreateOpen(true)}
          >
            新建数据集
          </Button>
        }
      />

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
          <ModalTitle>新建数据集</ModalTitle>
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

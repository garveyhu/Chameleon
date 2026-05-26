/** KB 文档表格：状态轮询 + 启停 + 批量(启停/重建/删) + 排序 + 状态筛选 */
import type { ReactElement } from 'react';
import { useMemo, useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertCircle,
  FileText,
  Globe,
  Loader2,
  Power,
  PowerOff,
  RotateCcw,
  ScrollText,
  Trash2,
} from 'lucide-react';

import {
  DataTable,
  type DataTableColumn,
  type SortOrder,
  TablePagination,
} from '@/core/components/table';
import { Switch } from '@/core/components/ui/switch';
import { Tooltip } from '@/core/components/ui/tooltip';
import { useSmartNavigate } from '@/core/hooks/use-smart-navigate';
import { cn } from '@/core/lib/cn';
import { confirm } from '@/core/lib/confirm';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { type BatchAction, documentApi } from '@/system/kbs/services/document';
import type { DocumentItem, DocumentStatus } from '@/system/kbs/types/kb';

interface Props {
  kbId: EntityId;
}

type SortBy = 'created_at' | 'token_count' | 'chunk_count';
type StatusFilter = '' | DocumentStatus;

const SOURCE_ICON: Record<DocumentItem['source_type'], ReactElement> = {
  upload: <FileText className="h-3.5 w-3.5" strokeWidth={1.6} />,
  url: <Globe className="h-3.5 w-3.5" strokeWidth={1.6} />,
  text: <ScrollText className="h-3.5 w-3.5" strokeWidth={1.6} />,
};

const STATUS_BADGE: Record<DocumentStatus, { label: string; cls: string }> = {
  pending: { label: '排队中', cls: 'bg-stone-100 text-stone-600' },
  processing: { label: '处理中', cls: 'bg-amber-50 text-amber-700' },
  ready: { label: '就绪', cls: 'bg-emerald-50 text-emerald-700' },
  failed: { label: '失败', cls: 'bg-rose-50 text-rose-700' },
};

const STATUS_FILTERS: { key: StatusFilter; label: string }[] = [
  { key: '', label: '全部' },
  { key: 'ready', label: '就绪' },
  { key: 'processing', label: '处理中' },
  { key: 'pending', label: '排队中' },
  { key: 'failed', label: '失败' },
];

const formatBytes = (n: number | null): string => {
  if (!n && n !== 0) return '-';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
};

export const DocumentTable = ({ kbId }: Props) => {
  const qc = useQueryClient();
  const smartNav = useSmartNavigate();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [sortBy, setSortBy] = useState<SortBy>('created_at');
  const [order, setOrder] = useState<SortOrder>('desc');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('');
  const [selected, setSelected] = useState<Set<EntityId>>(new Set());

  const listQ = useQuery({
    queryKey: ['kb-documents', kbId, page, pageSize, sortBy, order, statusFilter],
    queryFn: () =>
      documentApi.list(kbId, {
        page,
        page_size: pageSize,
        sort_by: sortBy,
        order,
        status: statusFilter || undefined,
      }),
    refetchInterval: q => {
      const rows = q.state.data?.items ?? [];
      return rows.some(d => d.status === 'pending' || d.status === 'processing') ? 2000 : false;
    },
  });

  const items = useMemo(() => listQ.data?.items ?? [], [listQ.data?.items]);

  const clearSel = () => setSelected(new Set());
  const invalidate = () => qc.invalidateQueries({ queryKey: ['kb-documents', kbId] });

  const toggleMut = useMutation({
    mutationFn: (v: { docId: EntityId; enabled: boolean }) =>
      documentApi.update(kbId, v.docId, { enabled: v.enabled }),
    onSuccess: (_d, v) => {
      toast.success(v.enabled ? '已启用（参与检索）' : '已停用（不参与检索）');
      invalidate();
    },
    onError: e => toast.error(`操作失败：${(e as Error).message}`),
  });

  const deleteMut = useMutation({
    mutationFn: (docId: EntityId) => documentApi.delete(kbId, docId),
    onSuccess: () => {
      toast.success('文档已删除');
      invalidate();
    },
  });

  const batchMut = useMutation({
    mutationFn: (action: BatchAction) => documentApi.batch(kbId, action, [...selected]),
    onSuccess: res => {
      const label: Record<BatchAction, string> = {
        enable: '已启用',
        disable: '已停用',
        delete: '已删除',
        reindex: '已排队重建',
      };
      toast.success(`${label[res.action]} ${res.affected} 个文档`);
      clearSel();
      invalidate();
    },
    onError: e => toast.error(`批量操作失败：${(e as Error).message}`),
  });

  const runBatch = async (action: BatchAction) => {
    if (selected.size === 0) return;
    if (action === 'delete') {
      const ok = await confirm({
        title: `删除选中的 ${selected.size} 个文档？`,
        description: '将同步清理切块与对象存储，不可恢复。',
        danger: true,
        confirmText: '删除',
      });
      if (!ok) return;
    }
    batchMut.mutate(action);
  };

  const toggleRow = (id: EntityId) =>
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const allChecked = items.length > 0 && items.every(d => selected.has(d.id));
  const someChecked = items.some(d => selected.has(d.id));

  const handleSort = (key: string, ord: SortOrder) => {
    setSortBy(key as SortBy);
    setOrder(ord);
    clearSel();
  };

  const changeStatus = (s: StatusFilter) => {
    setStatusFilter(s);
    setPage(1);
    clearSel();
  };

  const columns: DataTableColumn<DocumentItem>[] = [
    {
      key: 'select',
      header: (
        <input
          type="checkbox"
          className="accent-primary-600 h-3.5 w-3.5"
          checked={allChecked}
          ref={el => {
            if (el) el.indeterminate = someChecked && !allChecked;
          }}
          onChange={() => (allChecked ? clearSel() : setSelected(new Set(items.map(d => d.id))))}
        />
      ),
      width: 40,
      render: d => (
        <input
          type="checkbox"
          className="accent-primary-600 h-3.5 w-3.5"
          checked={selected.has(d.id)}
          onClick={e => e.stopPropagation()}
          onChange={() => toggleRow(d.id)}
        />
      ),
    },
    {
      key: 'title',
      header: '文档',
      render: d => (
        <div className={cn('flex items-center gap-2', !d.enabled && 'opacity-50')}>
          <span className="text-stone-500">{SOURCE_ICON[d.source_type]}</span>
          <span className="font-medium text-stone-900">{d.title}</span>
        </div>
      ),
    },
    {
      key: 'mime_size',
      header: '类型 / 大小',
      width: 130,
      render: d => (
        <span className="text-[11.5px] text-stone-500">
          {d.mime_type?.split(';')[0] || '-'}
          <span className="ml-1 font-mono text-stone-400">{formatBytes(d.size_bytes)}</span>
        </span>
      ),
    },
    {
      key: 'status',
      header: '状态',
      width: 110,
      render: d => <StatusCell doc={d} />,
    },
    {
      key: 'chunk_count',
      header: '切块',
      width: 80,
      align: 'right',
      sortable: true,
      render: d => (
        <span className="tnum font-mono text-[11.5px] text-stone-500">{d.chunk_count}</span>
      ),
    },
    {
      key: 'token_count',
      header: 'Token',
      width: 90,
      align: 'right',
      sortable: true,
      render: d => (
        <span className="tnum font-mono text-[11.5px] text-stone-500">{d.token_count}</span>
      ),
    },
    {
      key: 'created_at',
      header: '创建时间',
      width: 150,
      sortable: true,
      render: d => (
        <span className="tnum font-mono text-[11.5px] text-stone-500">
          {formatDateTime(d.created_at)}
        </span>
      ),
    },
    {
      key: 'enabled',
      header: '启用',
      width: 70,
      align: 'center',
      render: d => (
        <span className="inline-flex" onClick={e => e.stopPropagation()}>
          <Switch
            checked={d.enabled}
            disabled={toggleMut.isPending}
            onCheckedChange={v => toggleMut.mutate({ docId: d.id, enabled: v })}
          />
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      width: 50,
      render: d => (
        <button
          type="button"
          title="删除"
          className="rounded p-1 text-stone-500 hover:bg-rose-50 hover:text-rose-600"
          onClick={async e => {
            e.stopPropagation();
            if (
              await confirm({
                title: `删除文档 "${d.title}"？`,
                description: '将同步清理切块与对象存储，不可恢复。',
                danger: true,
                confirmText: '删除',
              })
            ) {
              deleteMut.mutate(d.id);
            }
          }}
        >
          <Trash2 className="h-3.5 w-3.5" strokeWidth={1.6} />
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex gap-1">
          {STATUS_FILTERS.map(f => (
            <button
              key={f.key || 'all'}
              type="button"
              onClick={() => changeStatus(f.key)}
              className={cn(
                'rounded-md px-2.5 py-1 text-[12px] transition',
                statusFilter === f.key
                  ? 'bg-stone-900 text-white'
                  : 'text-stone-500 hover:bg-stone-100',
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        {selected.size > 0 && (
          <BatchBar
            count={selected.size}
            pending={batchMut.isPending}
            onAction={runBatch}
            onClear={clearSel}
          />
        )}
      </div>

      <DataTable
        columns={columns}
        rows={items}
        rowKey="id"
        loading={listQ.isLoading}
        sortKey={sortBy}
        sortOrder={order}
        onSortChange={handleSort}
        emptyText="还没有文档，先上传一份吧"
        onRowClick={d =>
          smartNav(`/kbs/${kbId}/documents/${d.id}`, {
            prefetch: () =>
              Promise.all([
                qc.prefetchQuery({
                  queryKey: ['kb-doc', kbId, d.id],
                  queryFn: () => documentApi.get(kbId, d.id),
                }),
                qc.prefetchQuery({
                  queryKey: ['kb-doc-chunks', kbId, d.id],
                  queryFn: () => documentApi.listChunks(kbId, d.id, { page: 1, page_size: 200 }),
                }),
              ]),
          })
        }
      />
      <TablePagination
        page={page}
        pageSize={pageSize}
        total={listQ.data?.total ?? 0}
        onPageChange={p => {
          setPage(p);
          clearSel();
        }}
        onPageSizeChange={s => {
          setPageSize(s);
          setPage(1);
          clearSel();
        }}
      />
    </div>
  );
};

const BatchBar = ({
  count,
  pending,
  onAction,
  onClear,
}: {
  count: number;
  pending: boolean;
  onAction: (a: BatchAction) => void;
  onClear: () => void;
}) => (
  <div className="flex items-center gap-2 rounded-md border border-stone-200 bg-stone-50 px-2.5 py-1 text-[12px]">
    <span className="text-stone-600">已选 {count}</span>
    <span className="h-3 w-px bg-stone-300" />
    <BatchBtn
      icon={<Power className="h-3 w-3" />}
      label="启用"
      onClick={() => onAction('enable')}
      disabled={pending}
    />
    <BatchBtn
      icon={<PowerOff className="h-3 w-3" />}
      label="停用"
      onClick={() => onAction('disable')}
      disabled={pending}
    />
    <BatchBtn
      icon={<RotateCcw className="h-3 w-3" />}
      label="重建"
      onClick={() => onAction('reindex')}
      disabled={pending}
    />
    <BatchBtn
      icon={<Trash2 className="h-3 w-3" />}
      label="删除"
      onClick={() => onAction('delete')}
      disabled={pending}
      danger
    />
    <button type="button" onClick={onClear} className="ml-1 text-stone-400 hover:text-stone-700">
      取消
    </button>
  </div>
);

const BatchBtn = ({
  icon,
  label,
  onClick,
  disabled,
  danger,
}: {
  icon: ReactElement;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    className={cn(
      'inline-flex items-center gap-1 rounded px-1.5 py-0.5 transition disabled:opacity-50',
      danger ? 'text-rose-600 hover:bg-rose-50' : 'text-stone-600 hover:bg-stone-200/60',
    )}
  >
    {icon}
    {label}
  </button>
);

const StatusCell = ({ doc }: { doc: DocumentItem }) => {
  const badge = STATUS_BADGE[doc.status];
  const inner = (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${badge.cls}`}
    >
      {doc.status === 'processing' && <Loader2 className="h-3 w-3 animate-spin" strokeWidth={2} />}
      {doc.status === 'failed' && <AlertCircle className="h-3 w-3" strokeWidth={2} />}
      {badge.label}
    </span>
  );
  if (doc.status === 'failed' && doc.status_message) {
    return <Tooltip content={doc.status_message}>{inner}</Tooltip>;
  }
  return inner;
};

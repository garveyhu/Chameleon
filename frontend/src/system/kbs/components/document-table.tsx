/** KB 文档表格（带状态轮询） */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertCircle,
  FileText,
  Globe,
  Loader2,
  ScrollText,
  Trash2,
} from 'lucide-react';
import type { ReactElement } from 'react';
import { useEffect, useMemo, useState } from 'react';

import { useSmartNavigate } from '@/core/hooks/use-smart-navigate';

import {
  DataTable,
  type DataTableColumn,
  TablePagination,
} from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Tooltip } from '@/core/components/ui/tooltip';
import { confirm } from '@/core/lib/confirm';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import { documentApi } from '@/system/kbs/services/document';
import type {
  DocumentItem,
  DocumentStatus,
} from '@/system/kbs/types/kb';

interface Props {
  kbId: import('@/core/types/api').EntityId;
}

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

  const listQ = useQuery({
    queryKey: ['kb-documents', kbId, page, pageSize],
    queryFn: () => documentApi.list(kbId, { page, page_size: pageSize }),
  });

  const items = useMemo(
    () => listQ.data?.items ?? [],
    [listQ.data?.items],
  );
  const hasInflight = useMemo(
    () => items.some(d => d.status === 'pending' || d.status === 'processing'),
    [items],
  );

  // 状态轮询：有 pending/processing 时每 2s 刷新列表
  useEffect(() => {
    if (!hasInflight) return;
    const timer = setInterval(() => {
      qc.invalidateQueries({ queryKey: ['kb-documents', kbId] });
    }, 2000);
    return () => clearInterval(timer);
  }, [hasInflight, kbId, qc]);

  const deleteMut = useMutation({
    mutationFn: (docId: import('@/core/types/api').EntityId) =>
      documentApi.delete(kbId, docId),
    onSuccess: () => {
      toast.success('文档已删除');
      qc.invalidateQueries({ queryKey: ['kb-documents', kbId] });
    },
  });

  const columns: DataTableColumn<DocumentItem>[] = [
    {
      key: 'title',
      header: '文档',
      render: d => (
        <div className="flex items-center gap-2">
          <span className="text-stone-500">{SOURCE_ICON[d.source_type]}</span>
          <span className="font-medium text-stone-900">{d.title}</span>
        </div>
      ),
    },
    {
      key: 'mime_size',
      header: '类型 / 大小',
      width: 140,
      render: d => (
        <span className="text-[11.5px] text-stone-500">
          {d.mime_type?.split(';')[0] || '-'}
          <span className="ml-1 font-mono text-stone-400">
            {formatBytes(d.size_bytes)}
          </span>
        </span>
      ),
    },
    {
      key: 'status',
      header: '状态',
      width: 120,
      render: d => <StatusCell doc={d} />,
    },
    {
      key: 'stats',
      header: '切块 / Token',
      width: 130,
      render: d => (
        <span className="font-mono tnum text-[11.5px] text-stone-500">
          {d.chunk_count} · {d.token_count}
        </span>
      ),
    },
    {
      key: 'tags',
      header: '标签',
      width: 140,
      render: d =>
        d.tags.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {d.tags.slice(0, 3).map(t => (
              <Badge key={t} variant="outline" className="text-[10px]">
                {t}
              </Badge>
            ))}
            {d.tags.length > 3 && (
              <span className="text-[10px] text-stone-400">
                +{d.tags.length - 3}
              </span>
            )}
          </div>
        ) : (
          <span className="text-[11px] text-stone-300">—</span>
        ),
    },
    {
      key: 'created_at',
      header: '创建时间',
      width: 150,
      render: d => (
        <span className="tnum font-mono text-[11.5px] text-stone-500">
          {formatDateTime(d.created_at)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      width: 60,
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
    <div>
      <DataTable
        columns={columns}
        rows={items}
        rowKey="id"
        loading={listQ.isLoading}
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
                  queryFn: () =>
                    documentApi.listChunks(kbId, d.id, { page: 1, page_size: 200 }),
                }),
              ]),
          })
        }
      />
      <TablePagination
        page={page}
        pageSize={pageSize}
        total={listQ.data?.total ?? 0}
        onPageChange={setPage}
        onPageSizeChange={s => {
          setPageSize(s);
          setPage(1);
        }}
      />
    </div>
  );
};

const StatusCell = ({ doc }: { doc: DocumentItem }) => {
  const badge = STATUS_BADGE[doc.status];
  const inner = (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${badge.cls}`}
    >
      {doc.status === 'processing' && (
        <Loader2 className="h-3 w-3 animate-spin" strokeWidth={2} />
      )}
      {doc.status === 'failed' && (
        <AlertCircle className="h-3 w-3" strokeWidth={2} />
      )}
      {badge.label}
    </span>
  );
  if (doc.status === 'failed' && doc.status_message) {
    return <Tooltip content={doc.status_message}>{inner}</Tooltip>;
  }
  return inner;
};

/** 知识库管理页 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, Library } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { EmptyState } from '@/core/components/common/empty-state';
import {
  DataTable,
  type DataTableColumn,
  SectionCard,
  TablePagination,
  TableToolbar,
} from '@/core/components/table';
import { useSmartNavigate } from '@/core/hooks/use-smart-navigate';
import { formatDateTime } from '@/core/lib/format';
import { documentApi } from '@/system/kbs/services/document';
import { kbApi } from '@/system/kbs/services/kb';
import type { KbItem } from '@/system/kbs/types/kb';

export const KbsPage = () => {
  const { t } = useTranslation();
  const smartNav = useSmartNavigate();
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const listQ = useQuery({
    queryKey: ['kbs', page, pageSize],
    queryFn: () => kbApi.list({ page, page_size: pageSize }),
  });

  const columns: DataTableColumn<KbItem>[] = [
    {
      key: 'kb_key',
      header: t('table.kb_key'),
      width: 160,
      render: k => (
        <span className="font-mono text-[11.5px] text-stone-700">{k.kb_key}</span>
      ),
    },
    {
      key: 'name',
      header: t('common.name'),
      render: k => <span className="font-medium text-stone-900">{k.name}</span>,
    },
    {
      key: 'embedding',
      header: t('table.embedding'),
      render: k => (
        <span className="text-[11.5px] text-stone-500">
          {k.embedding_model}
          <span className="ml-2 font-mono tnum">d={k.embedding_dim}</span>
        </span>
      ),
    },
    {
      key: 'stats',
      header: t('table.stats'),
      width: 160,
      render: k => (
        <span className="tnum font-mono text-[11.5px] text-stone-500">
          {k.document_count} 文档 · {k.chunk_count} 切块
        </span>
      ),
    },
    {
      key: 'created_at',
      header: t('common.created_at'),
      width: 160,
      render: k => (
        <span className="tnum font-mono text-[11.5px] text-stone-500">
          {formatDateTime(k.created_at)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      width: 60,
      render: () => (
        <ArrowRight className="ml-auto h-3.5 w-3.5 text-stone-400" strokeWidth={1.6} />
      ),
    },
  ];

  return (
    <SectionCard>
      <TableToolbar title={t('page.kbs_title')} />
      <DataTable
        columns={columns}
        rows={listQ.data?.items || []}
        rowKey="id"
        loading={listQ.isLoading}
        emptyText={
          <EmptyState icon={<Library strokeWidth={1.5} />} title={t('empty.kbs')} />
        }
        onRowClick={k =>
          smartNav(`/kbs/${k.id}`, {
            prefetch: () =>
              Promise.all([
                qc.prefetchQuery({
                  queryKey: ['kb', k.id],
                  queryFn: () => kbApi.get(k.id),
                }),
                qc.prefetchQuery({
                  queryKey: ['kb-documents', k.id, 1, 20],
                  queryFn: () =>
                    documentApi.list(k.id, { page: 1, page_size: 20 }),
                }),
              ]),
          })
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
  );
};

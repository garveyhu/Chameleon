/** 知识库管理页 */

import { useQuery } from '@tanstack/react-query';
import { Database, Library } from 'lucide-react';
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
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import { formatDateTime, truncate } from '@/core/lib/format';
import { kbApi } from '@/system/kbs/services/kb';
import type { KbItem } from '@/system/kbs/types/kb';

export const KbsPage = () => {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [viewKb, setViewKb] = useState<KbItem | null>(null);
  const listQ = useQuery({
    queryKey: ['kbs', page, pageSize],
    queryFn: () => kbApi.list({ page, page_size: pageSize }),
  });

  const columns: DataTableColumn<KbItem>[] = [
    { key: 'kb_key', header: t('table.kb_key'), width: 160, render: k => <span className="font-mono text-[11.5px] text-stone-700">{k.kb_key}</span> },
    { key: 'name', header: t('common.name'), render: k => <span className="font-medium text-stone-900">{k.name}</span> },
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
      render: k => <span className="tnum font-mono text-[11.5px] text-stone-500">{formatDateTime(k.created_at)}</span>,
    },
    {
      key: 'actions',
      header: t('common.actions'),
      align: 'right',
      width: 100,
      render: k => (
        <button
          type="button"
          title="查看切块"
          className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-[11.5px] text-stone-600 hover:bg-stone-200 hover:text-stone-900"
          onClick={() => setViewKb(k)}
        >
          <Database className="h-3.5 w-3.5" /> 切块
        </button>
      ),
    },
  ];

  return (
    <div>
      <SectionCard>
        <TableToolbar title={t('page.kbs_title')} />
        <DataTable
          columns={columns}
          rows={listQ.data?.items || []}
          rowKey="id"
          loading={listQ.isLoading}
          emptyText={
            <EmptyState
              icon={<Library strokeWidth={1.5} />}
              title={t('empty.kbs')}
            />
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
      <ChunksSheet kb={viewKb} onClose={() => setViewKb(null)} />
    </div>
  );
};

const ChunksSheet = ({ kb, onClose }: { kb: KbItem | null; onClose: () => void }) => {
  const [page, setPage] = useState(1);
  const chunksQ = useQuery({
    queryKey: ['kb-chunks', kb?.id, page],
    queryFn: () => kbApi.listChunks(kb!.id, { page, page_size: 20 }),
    enabled: !!kb,
  });

  return (
    <Sheet
      open={!!kb}
      onOpenChange={o => {
        if (!o) {
          setPage(1);
          onClose();
        }
      }}
    >
      <SheetContent width="w-[640px]">
        <SheetHeader>
          <SheetTitle>{kb?.name} · 切块</SheetTitle>
        </SheetHeader>
        <SheetBody className="space-y-2">
          {(chunksQ.data?.items || []).map(c => (
            <div
              key={c.id}
              className="rounded-md border border-stone-200 bg-stone-50 p-3 text-sm"
            >
              <div className="mb-1 flex items-center justify-between text-xs text-stone-500">
                <span className="font-mono">doc:{c.document_id} #{c.chunk_index}</span>
                <Badge variant="outline">{formatDateTime(c.created_at)}</Badge>
              </div>
              <div className="whitespace-pre-wrap">{truncate(c.content, 400)}</div>
            </div>
          ))}
        </SheetBody>
        <SheetFooter>
          <span className="mr-auto text-xs text-stone-500">
            共 {chunksQ.data?.total ?? 0} 条
          </span>
          <Button variant="ghost" onClick={onClose}>
            关闭
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
};

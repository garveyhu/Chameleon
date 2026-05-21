/** 知识库管理页 */

import { useQuery } from '@tanstack/react-query';
import { Database } from 'lucide-react';
import { useState } from 'react';

import { DataTable, type DataTableColumn } from '@/core/components/common/data-table';
import { PageHeader } from '@/core/components/common/page-header';
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
  const [page, setPage] = useState(1);
  const [viewKb, setViewKb] = useState<KbItem | null>(null);
  const listQ = useQuery({
    queryKey: ['kbs', page],
    queryFn: () => kbApi.list({ page, page_size: 20 }),
  });

  const columns: DataTableColumn<KbItem>[] = [
    { key: 'kb_key', title: 'kb_key', render: k => <span className="font-mono">{k.kb_key}</span> },
    { key: 'name', title: '名称' },
    {
      key: 'embedding',
      title: 'embedding',
      render: k => (
        <span className="text-xs text-stone-500">
          {k.embedding_model}
          <span className="ml-2 font-mono">d={k.embedding_dim}</span>
        </span>
      ),
    },
    {
      key: 'stats',
      title: '统计',
      render: k => (
        <span className="text-xs text-stone-500">
          {k.document_count} 文档 · {k.chunk_count} 切块
        </span>
      ),
    },
    {
      key: 'created_at',
      title: '创建时间',
      render: k => <span className="text-xs text-stone-500">{formatDateTime(k.created_at)}</span>,
    },
    {
      key: 'actions',
      title: '操作',
      align: 'right',
      width: '120px',
      render: k => (
        <Button size="sm" variant="ghost" onClick={() => setViewKb(k)}>
          <Database className="h-3.5 w-3.5" /> 切块
        </Button>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title="知识库" description="业务方通过 /v1/knowledge 创建；这里查看与管理" />
      <DataTable
        columns={columns}
        data={listQ.data?.items || []}
        loading={listQ.isLoading}
        pagination={{ page, pageSize: 20, total: listQ.data?.total || 0, onPageChange: setPage }}
      />
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

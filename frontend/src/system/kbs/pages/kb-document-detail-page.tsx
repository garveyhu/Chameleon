/** 文档详情页：信息卡（标签 / 元数据字段填值）+ chunk 卡片墙（搜索 + 分页） */
import type { ReactElement } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, FileText, Globe, RotateCcw, ScrollText, Search, X } from 'lucide-react';

import { SectionCard, TablePagination } from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import { ChunkCard } from '@/system/kbs/components/chunk-card';
import { DocMetaFields } from '@/system/kbs/components/doc-meta-fields';
import { TagEditor } from '@/system/kbs/components/tag-editor';
import { documentApi } from '@/system/kbs/services/document';
import type { DocumentItem } from '@/system/kbs/types/kb';

const SOURCE_ICON: Record<DocumentItem['source_type'], ReactElement> = {
  upload: <FileText className="h-3.5 w-3.5" strokeWidth={1.6} />,
  url: <Globe className="h-3.5 w-3.5" strokeWidth={1.6} />,
  text: <ScrollText className="h-3.5 w-3.5" strokeWidth={1.6} />,
};

export const KbDocumentDetailPage = () => {
  const { id, docId } = useParams<{ id: string; docId: string }>();
  const kbId = id ?? '';
  const docIdNum = docId ?? '';
  const valid = !!kbId && !!docIdNum;

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(12);
  const [searchInput, setSearchInput] = useState('');
  const [q, setQ] = useState('');

  const docQ = useQuery({
    queryKey: ['kb-doc', kbId, docIdNum],
    queryFn: () => documentApi.get(kbId, docIdNum),
    enabled: valid,
  });

  const chunksQ = useQuery({
    queryKey: ['kb-doc-chunks', kbId, docIdNum, page, pageSize, q],
    queryFn: () =>
      documentApi.listChunks(kbId, docIdNum, {
        page,
        page_size: pageSize,
        q: q || undefined,
      }),
    enabled: valid,
  });

  const applySearch = (next: string) => {
    setQ(next.trim());
    setPage(1);
  };

  if (!valid) {
    return (
      <SectionCard>
        <div className="p-6 text-sm text-stone-500">非法的路径参数</div>
      </SectionCard>
    );
  }

  const doc = docQ.data ?? null;
  const chunks = chunksQ.data?.items ?? [];
  const total = chunksQ.data?.total ?? 0;

  return (
    <div className="space-y-3">
      <Breadcrumb kbId={kbId} doc={doc} />
      {doc && <DocumentInfoCard doc={doc} />}
      <SectionCard>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="shrink-0 text-[14px] font-medium text-stone-900">切块卡片墙</h3>
          <div className="relative max-w-[280px] flex-1">
            <Search className="absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-stone-400" />
            <Input
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && applySearch(searchInput)}
              placeholder="搜索切块内容…"
              className="h-8 pr-7 pl-8 text-[12.5px]"
            />
            {searchInput && (
              <button
                type="button"
                onClick={() => {
                  setSearchInput('');
                  applySearch('');
                }}
                className="absolute top-1/2 right-2 -translate-y-1/2 text-stone-400 hover:text-stone-600"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <span className="shrink-0 text-[11.5px] text-stone-500">
            {q ? `命中 ${total} 块` : `共 ${total} 块`}
          </span>
        </div>
        {chunksQ.isLoading ? (
          <div className="py-10 text-center text-sm text-stone-400">加载中…</div>
        ) : chunks.length === 0 ? (
          <div className="py-12 text-center text-sm text-stone-400">
            {q ? `没有匹配「${q}」的切块` : '尚无切块；上传完成后会自动出现'}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {chunks.map(c => (
                <ChunkCard key={String(c.id)} chunk={c} kbId={kbId} docId={docIdNum} />
              ))}
            </div>
            <div className="mt-3">
              <TablePagination
                page={page}
                pageSize={pageSize}
                total={total}
                onPageChange={setPage}
                onPageSizeChange={s => {
                  setPageSize(s);
                  setPage(1);
                }}
              />
            </div>
          </>
        )}
      </SectionCard>
    </div>
  );
};

const Breadcrumb = ({ kbId, doc }: { kbId: string | number; doc: DocumentItem | null }) => (
  <div className="flex items-center gap-2 text-[12.5px] text-stone-500">
    <Link
      to="/kbs"
      className="inline-flex items-center gap-1 rounded-md px-2 py-1 hover:bg-stone-100 hover:text-stone-800"
    >
      <ArrowLeft className="h-3.5 w-3.5" /> 知识库
    </Link>
    <span className="text-stone-300">/</span>
    <Link to={`/kbs/${kbId}`} className="hover:underline">
      KB {kbId}
    </Link>
    <span className="text-stone-300">/</span>
    <span className="text-stone-700">{doc ? doc.title : '文档…'}</span>
  </div>
);

const DocumentInfoCard = ({ doc }: { doc: DocumentItem }) => {
  const qc = useQueryClient();
  const [tags, setTags] = useState<string[]>(doc.tags);
  const [meta, setMeta] = useState<Record<string, unknown>>(doc.meta ?? {});
  // 文档刷新时同步内部状态（合法的服务端→本地态同步）
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setTags(doc.tags), [doc.tags]);
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setMeta(doc.meta ?? {}), [doc.meta]);

  const dirty = useMemo(
    () =>
      JSON.stringify(tags) !== JSON.stringify(doc.tags) ||
      JSON.stringify(meta) !== JSON.stringify(doc.meta ?? {}),
    [tags, meta, doc.tags, doc.meta],
  );

  const saveMut = useMutation({
    mutationFn: () => documentApi.update(doc.kb_id, doc.id, { tags, meta }),
    onSuccess: () => {
      toast.success('文档信息已保存');
      qc.invalidateQueries({ queryKey: ['kb-doc', doc.kb_id, doc.id] });
    },
  });

  const reindexMut = useMutation({
    mutationFn: () => documentApi.reindex(doc.kb_id, doc.id),
    onSuccess: () => {
      toast.success('已排队重分块');
      qc.invalidateQueries({ queryKey: ['kb-doc', doc.kb_id, doc.id] });
      qc.invalidateQueries({ queryKey: ['kb-doc-chunks', doc.kb_id, doc.id] });
    },
  });

  return (
    <SectionCard>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-stone-500">{SOURCE_ICON[doc.source_type]}</span>
            <h2 className="truncate text-[16px] font-medium text-stone-900">{doc.title}</h2>
            <StatusBadge status={doc.status} />
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-stone-500">
            <span>类型: {doc.mime_type ?? '—'}</span>
            <span>来源: {doc.source_type}</span>
            {doc.size_bytes != null && <span>大小: {(doc.size_bytes / 1024).toFixed(1)} KB</span>}
            <span>
              统计:{' '}
              <span className="tnum font-mono">
                {doc.chunk_count} chunks · {doc.token_count} tokens
              </span>
            </span>
            <span>创建: {formatDateTime(doc.created_at)}</span>
          </div>
          {doc.status === 'failed' && doc.status_message && (
            <div className="mt-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-[11.5px] text-rose-700">
              {doc.status_message}
            </div>
          )}
          <div className="mt-3 space-y-3">
            <div>
              <div className="mb-1 text-[11.5px] text-stone-600">标签</div>
              <TagEditor value={tags} onChange={setTags} />
            </div>
            <div>
              <div className="mb-1 text-[11.5px] text-stone-600">元数据</div>
              <DocMetaFields kbId={doc.kb_id} value={meta} onChange={setMeta} />
            </div>
          </div>
        </div>
        <div className="flex shrink-0 flex-col gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => reindexMut.mutate()}
            disabled={reindexMut.isPending || doc.status === 'processing'}
          >
            <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
            重新分块
          </Button>
          <Button size="sm" onClick={() => saveMut.mutate()} disabled={!dirty || saveMut.isPending}>
            保存修改
          </Button>
        </div>
      </div>
    </SectionCard>
  );
};

const StatusBadge = ({ status }: { status: DocumentItem['status'] }) => {
  const map: Record<DocumentItem['status'], { label: string; cls: string }> = {
    pending: { label: '排队中', cls: 'bg-stone-100 text-stone-600' },
    processing: { label: '处理中', cls: 'bg-amber-50 text-amber-700' },
    ready: { label: '就绪', cls: 'bg-emerald-50 text-emerald-700' },
    failed: { label: '失败', cls: 'bg-rose-50 text-rose-700' },
  };
  const b = map[status];
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-[10.5px] font-medium',
        b.cls,
      )}
    >
      {b.label}
    </span>
  );
};

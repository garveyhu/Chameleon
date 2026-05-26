/** 知识库列表 —— Dify 式卡片网格 + 创建入口卡 */
import { useNavigate } from 'react-router-dom';

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Database, FileText, Layers, Plus } from 'lucide-react';

import { documentApi } from '@/system/kbs/services/document';
import { kbApi } from '@/system/kbs/services/kb';
import type { KbItem } from '@/system/kbs/types/kb';

export const KbsPage = () => {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['kbs', 1, 100],
    queryFn: () => kbApi.list({ page: 1, page_size: 100 }),
  });
  const items = listQ.data?.items ?? [];

  const open = (k: KbItem) => {
    void qc.prefetchQuery({
      queryKey: ['kb-documents', k.id, 1, 20],
      queryFn: () => documentApi.list(k.id, { page: 1, page_size: 20 }),
    });
    navigate(`/kbs/${k.id}`);
  };

  return (
    <div className="px-1">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-[16px] font-semibold text-stone-900">知识库</h1>
        <span className="text-[12px] text-stone-400">
          {listQ.data ? `共 ${listQ.data.total} 个` : ''}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {/* 创建入口卡 */}
        <button
          type="button"
          onClick={() => navigate('/kbs/create')}
          className="group flex h-[132px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-stone-300 bg-white/60 text-stone-500 transition hover:border-blue-400 hover:bg-blue-50/40 hover:text-blue-600"
        >
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-stone-100 transition group-hover:bg-blue-100">
            <Plus className="h-5 w-5" strokeWidth={1.75} />
          </div>
          <span className="text-[13px] font-medium">创建知识库</span>
          <span className="text-[11px] text-stone-400">导入文档，自动分段 + 向量化</span>
        </button>

        {/* 知识库卡片 */}
        {items.map(k => (
          <button
            key={k.id}
            type="button"
            onClick={() => open(k)}
            className="group flex h-[132px] flex-col rounded-xl border border-stone-200/80 bg-white p-4 text-left shadow-sm transition hover:border-stone-300 hover:shadow-md"
          >
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600">
                <Database className="h-5 w-5" strokeWidth={1.75} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13.5px] font-medium text-stone-900">{k.name}</div>
                <div className="truncate font-mono text-[10.5px] text-stone-400">{k.kb_key}</div>
              </div>
            </div>
            <p className="mt-2 line-clamp-2 flex-1 text-[11.5px] leading-relaxed text-stone-500">
              {k.description || '暂无描述'}
            </p>
            <div className="mt-auto flex items-center gap-3 text-[11px] text-stone-400">
              <span className="inline-flex items-center gap-1">
                <FileText className="h-3 w-3" />
                {k.document_count} 文档
              </span>
              <span className="inline-flex items-center gap-1">
                <Layers className="h-3 w-3" />
                {k.chunk_count} 切块
              </span>
              <span className="ml-auto truncate font-mono">{k.embedding_model}</span>
            </div>
          </button>
        ))}

        {/* 加载骨架 */}
        {listQ.isLoading &&
          items.length === 0 &&
          Array.from({ length: 3 }).map((_, i) => (
            <div key={`skl-${i}`} className="skeleton h-[132px] rounded-xl opacity-60" />
          ))}
      </div>
    </div>
  );
};

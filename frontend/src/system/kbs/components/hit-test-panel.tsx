/** 检索测试三栏：参数 / 命中 chunk 列表 / 选中原文 + score breakdown
 *
 * 状态全在 core/stores/kb（query/topK/mode/multiQuery/tags/hits/selectedChunkId）。
 * score breakdown 依赖 Agent B 的 B6 API；未接入时仅显综合得分。
 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { useMutation, useQuery } from '@tanstack/react-query';
import { FlaskConical, Search, SearchX } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { Switch } from '@/core/components/ui/switch';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { get } from '@/core/lib/request';
import { toast } from '@/core/lib/toast';
import { selectedHit, useKbStore } from '@/core/stores/kb';
import { ScoreBreakdown } from '@/system/kbs/components/score-breakdown';
import { documentApi } from '@/system/kbs/services/document';
import type { KbItem, KbMetadataField, RecallMode, SearchHitItem } from '@/system/kbs/types/kb';
import { highlight } from '@/system/kbs/utils/highlight';

interface Props {
  kb: KbItem;
}

export const HitTestPanel = ({ kb }: Props) => {
  const query = useKbStore(s => s.query);
  const topK = useKbStore(s => s.topK);
  const mode = useKbStore(s => s.mode);
  const tags = useKbStore(s => s.tags);
  const multiQuery = useKbStore(s => s.multiQuery);
  const hits = useKbStore(s => s.hits);
  const selectedChunkId = useKbStore(s => s.selectedChunkId);
  const current = useKbStore(selectedHit);
  const setQuery = useKbStore(s => s.setQuery);
  const setTopK = useKbStore(s => s.setTopK);
  const setMode = useKbStore(s => s.setMode);
  const setTags = useKbStore(s => s.setTags);
  const setMultiQuery = useKbStore(s => s.setMultiQuery);
  const setHits = useKbStore(s => s.setHits);
  const selectChunk = useKbStore(s => s.selectChunk);
  const reset = useKbStore(s => s.reset);

  const [metaFilters, setMetaFilters] = useState<Record<string, string>>({});

  const fieldsQ = useQuery({
    queryKey: ['kb-metadata-fields', kb.id],
    queryFn: () => get<KbMetadataField[]>(`/v1/admin/kbs/${kb.id}/metadata-fields`),
  });
  const fields = fieldsQ.data ?? [];

  useEffect(() => {
    reset({ topK: kb.default_top_k, mode: kb.recall_mode });
    // 切换 KB 时清空本地过滤（合法的 reset-on-prop-change）
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMetaFilters({});
  }, [kb.id, kb.default_top_k, kb.recall_mode, reset]);

  const searchMut = useMutation({
    mutationFn: () => {
      const activeMeta = Object.fromEntries(
        Object.entries(metaFilters).filter(([, v]) => v.trim()),
      );
      return documentApi.search(kb.id, {
        query: query.trim(),
        top_k: topK,
        mode,
        multi_query_count: multiQuery ? 3 : undefined,
        tags: tags.trim()
          ? tags
              .split(',')
              .map(t => t.trim())
              .filter(Boolean)
          : undefined,
        metadata_filters: Object.keys(activeMeta).length ? activeMeta : undefined,
      });
    },
    onSuccess: rows => {
      setHits(rows);
      if (rows.length === 0) {
        toast.info('未命中任何 chunk，试着降低 top_k 或换 query');
      }
    },
  });

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-[260px_minmax(0,1fr)_minmax(0,1.05fr)]">
      {/* ① 参数 */}
      <div className="space-y-3">
        <Field label="查询语句">
          <Textarea
            value={query}
            onChange={e => setQuery(e.target.value)}
            rows={5}
            placeholder="输入要检索的问题或关键词…"
          />
        </Field>
        <Field
          label={
            <>
              top_k = <span className="tnum font-mono">{topK}</span>
            </>
          }
        >
          <input
            type="range"
            min={1}
            max={20}
            value={topK}
            onChange={e => setTopK(Number(e.target.value))}
            className="w-full accent-amber-600"
          />
        </Field>
        <Field label="召回模式">
          <Select value={mode} onValueChange={v => setMode(v as RecallMode)}>
            <SelectTrigger className="h-8 text-[12.5px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="vector">向量（语义检索）</SelectItem>
              <SelectItem value="hybrid">混合（向量 + 关键词）</SelectItem>
              <SelectItem value="keyword">关键词（BM25）</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <label className="flex items-center justify-between gap-2 text-[12px] text-stone-600">
          <span>多查询扩展</span>
          <Switch checked={multiQuery} onCheckedChange={setMultiQuery} />
        </label>
        <Field label="标签过滤（多个用逗号）">
          <Input
            value={tags}
            onChange={e => setTags(e.target.value)}
            placeholder="product, faq"
            className="h-8 text-[12.5px]"
          />
        </Field>
        {fields.length > 0 && (
          <Field label="元数据过滤">
            <div className="space-y-1.5">
              {fields.map(f => (
                <div key={f.id} className="flex items-center gap-2">
                  <span className="w-16 shrink-0 truncate text-[11px] text-stone-500">
                    {f.label}
                  </span>
                  {f.field_type === 'select' && f.options ? (
                    <Select
                      value={metaFilters[f.key] ?? '__any__'}
                      onValueChange={v =>
                        setMetaFilters(m => ({
                          ...m,
                          [f.key]: v === '__any__' ? '' : v,
                        }))
                      }
                    >
                      <SelectTrigger className="h-7 text-[11.5px]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__any__">不限</SelectItem>
                        {f.options.map(o => (
                          <SelectItem key={o} value={o}>
                            {o}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      value={metaFilters[f.key] ?? ''}
                      onChange={e => setMetaFilters(m => ({ ...m, [f.key]: e.target.value }))}
                      placeholder={`按 ${f.label} 过滤`}
                      className="h-7 text-[11.5px]"
                    />
                  )}
                </div>
              ))}
            </div>
          </Field>
        )}
        <Button
          className="w-full"
          onClick={() => searchMut.mutate()}
          disabled={!query.trim() || searchMut.isPending}
        >
          <Search className="mr-1 h-3.5 w-3.5" />
          {searchMut.isPending ? '检索中…' : '搜索'}
        </Button>
        {import.meta.env.DEV && (
          <Button
            variant="ghost"
            className="w-full text-[11.5px] text-stone-500"
            onClick={() => setHits(mockHits())}
          >
            <FlaskConical className="mr-1 h-3.5 w-3.5" />
            插入示例命中（dev）
          </Button>
        )}
      </div>

      {/* ② 命中 chunk 列表 */}
      <div className="min-h-[280px] space-y-2">
        {searchMut.isPending ? (
          <Centered>正在检索…</Centered>
        ) : hits.length === 0 ? (
          <Centered icon>
            {searchMut.isSuccess ? '未命中任何 chunk' : '输入 query 后开始检索'}
          </Centered>
        ) : (
          hits.map((h, idx) => (
            <HitCard
              key={String(h.chunk_id)}
              hit={h}
              rank={idx + 1}
              active={String(h.chunk_id) === String(selectedChunkId)}
              onClick={() => selectChunk(h.chunk_id)}
            />
          ))
        )}
      </div>

      {/* ③ 选中原文 + 分项得分 */}
      <div className="rounded-lg border border-stone-200/70 bg-white">
        {current ? (
          <SourceView hit={current} kbId={kb.id} query={query} />
        ) : (
          <Centered icon>选中左侧 chunk 查看原文与分项得分</Centered>
        )}
      </div>
    </div>
  );
};

const Field = ({ label, children }: { label: React.ReactNode; children: React.ReactNode }) => (
  <div>
    <label className="mb-1 block text-[12px] text-stone-600">{label}</label>
    {children}
  </div>
);

const Centered = ({ children, icon }: { children: React.ReactNode; icon?: boolean }) => (
  <div className="flex h-full min-h-[240px] flex-col items-center justify-center gap-2 text-stone-400">
    {icon && <SearchX className="h-8 w-8" strokeWidth={1.4} />}
    <div className="px-4 text-center text-[12.5px]">{children}</div>
  </div>
);

const HitCard = ({
  hit,
  rank,
  active,
  onClick,
}: {
  hit: SearchHitItem;
  rank: number;
  active: boolean;
  onClick: () => void;
}) => (
  <button
    type="button"
    onClick={onClick}
    className={cn(
      'block w-full rounded-lg border bg-white p-2.5 text-left transition',
      active
        ? 'border-amber-300 ring-1 ring-amber-200'
        : 'border-stone-200/70 hover:border-amber-200',
    )}
  >
    <div className="mb-1.5 flex items-center gap-2 text-[11px] text-stone-500">
      <span className="font-mono">#{rank}</span>
      <span className="truncate">{hit.document_title}</span>
      <span className="ml-auto shrink-0 font-mono">seq {hit.seq}</span>
    </div>
    <ScoreBreakdown hit={hit} compact />
    <div className="mt-1.5 line-clamp-2 text-[12px] leading-snug text-stone-700">{hit.content}</div>
  </button>
);

const SourceView = ({
  hit,
  kbId,
  query,
}: {
  hit: SearchHitItem;
  kbId: KbItem['id'];
  query: string;
}) => (
  <div className="flex h-full flex-col">
    <div className="border-b border-stone-200/70 p-3">
      <div className="mb-2 flex items-center gap-2 text-[11.5px] text-stone-600">
        <Link
          to={`/kbs/${kbId}/documents/${hit.doc_id}`}
          className="truncate font-medium hover:underline"
        >
          {hit.document_title}
        </Link>
        <span className="ml-auto shrink-0 font-mono text-[10.5px] text-stone-400">
          seq {hit.seq}
        </span>
      </div>
      <ScoreBreakdown hit={hit} />
    </div>
    <div
      className="flex-1 overflow-y-auto p-3 text-[12.5px] leading-relaxed whitespace-pre-wrap text-stone-800"
      dangerouslySetInnerHTML={{ __html: highlight(hit.content, query) }}
    />
  </div>
);

/** dev 预览用示例命中（含 B6 分项），不参与生产构建 */
function mockHits(): SearchHitItem[] {
  return [
    {
      chunk_id: 'mock-1',
      doc_id: 'doc-1',
      seq: 3,
      score: 0.92,
      document_title: '产品手册.pdf',
      content:
        '变色龙平台支持多源模型统一聚合，通过统一网关路由到不同的上游 provider，并按 workspace 计费。',
      vector_score: 0.88,
      bm25_score: 0.61,
      rerank_score: 0.95,
    },
    {
      chunk_id: 'mock-2',
      doc_id: 'doc-1',
      seq: 7,
      score: 0.78,
      document_title: '产品手册.pdf',
      content: '检索增强生成（RAG）先从知识库召回相关切块，再拼进 prompt 交给大模型生成答案。',
      vector_score: 0.81,
      bm25_score: 0.44,
      rerank_score: 0.72,
    },
    {
      chunk_id: 'mock-3',
      doc_id: 'doc-2',
      seq: 1,
      score: 0.55,
      document_title: 'FAQ.md',
      content: '如何配置 reranker？在知识库 collection 配置里选择 BGE 或 Cohere。',
      vector_score: 0.49,
      bm25_score: 0.7,
      rerank_score: 0.58,
    },
  ];
}

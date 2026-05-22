/** 检索测试 playground —— 左侧 query 配置 / 右侧命中卡片 */

import { useMutation } from '@tanstack/react-query';
import { Search, SearchX } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import { documentApi } from '@/system/kbs/services/document';
import type {
  KbItem,
  RecallMode,
  SearchHitItem,
} from '@/system/kbs/types/kb';

interface Props {
  kb: KbItem;
}

export const RetrievalTest = ({ kb }: Props) => {
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState(kb.default_top_k);
  const [mode, setMode] = useState<RecallMode>(kb.recall_mode);
  const [tagsInput, setTagsInput] = useState('');
  const [hits, setHits] = useState<SearchHitItem[]>([]);

  const searchMut = useMutation({
    mutationFn: () =>
      documentApi.search(kb.id, {
        query: query.trim(),
        top_k: topK,
        mode,
        tags: tagsInput.trim()
          ? tagsInput
              .split(',')
              .map(t => t.trim())
              .filter(Boolean)
          : undefined,
      }),
    onSuccess: rows => {
      setHits(rows);
      if (rows.length === 0) {
        toast.info('未命中任何 chunk，试着降低 top_k 或换 query');
      }
    },
  });

  return (
    <div className="grid grid-cols-[320px_1fr] gap-4">
      {/* 左侧：query 配置 */}
      <div className="space-y-3">
        <div>
          <label className="mb-1 block text-[12px] text-stone-600">Query</label>
          <Textarea
            value={query}
            onChange={e => setQuery(e.target.value)}
            rows={5}
            placeholder="输入查询语句…"
          />
        </div>
        <div>
          <label className="mb-1 block text-[12px] text-stone-600">
            top_k = <span className="font-mono tnum">{topK}</span>
          </label>
          <input
            type="range"
            min={1}
            max={20}
            value={topK}
            onChange={e => setTopK(Number(e.target.value))}
            className="w-full accent-amber-600"
          />
        </div>
        <div>
          <label className="mb-1 block text-[12px] text-stone-600">召回模式</label>
          <Select value={mode} onValueChange={v => setMode(v as RecallMode)}>
            <SelectTrigger className="h-8 text-[12.5px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="vector">vector（语义）</SelectItem>
              <SelectItem value="hybrid">hybrid（混合）</SelectItem>
              <SelectItem value="keyword">keyword（关键词）</SelectItem>
            </SelectContent>
          </Select>
          {mode !== 'vector' && (
            <p className="mt-1 text-[10.5px] text-amber-700">
              hybrid / keyword 后端在 Bundle 4 实装，当前仍按 vector 行为
            </p>
          )}
        </div>
        <div>
          <label className="mb-1 block text-[12px] text-stone-600">
            标签过滤（多个用逗号）
          </label>
          <Input
            value={tagsInput}
            onChange={e => setTagsInput(e.target.value)}
            placeholder="product, faq"
            className="h-8 text-[12.5px]"
          />
        </div>
        <Button
          className="w-full"
          onClick={() => searchMut.mutate()}
          disabled={!query.trim() || searchMut.isPending}
        >
          <Search className="mr-1 h-3.5 w-3.5" />
          {searchMut.isPending ? '检索中…' : '搜索'}
        </Button>
      </div>

      {/* 右侧：命中卡片 */}
      <div className="space-y-2">
        {searchMut.isPending ? (
          <div className="py-10 text-center text-sm text-stone-400">
            正在检索…
          </div>
        ) : hits.length === 0 ? (
          <div className="flex h-[260px] flex-col items-center justify-center gap-2 text-stone-400">
            <SearchX className="h-8 w-8" strokeWidth={1.4} />
            <div className="text-[12.5px]">
              {searchMut.isSuccess
                ? '未命中任何 chunk'
                : '输入 query 后开始检索'}
            </div>
          </div>
        ) : (
          hits.map((h, idx) => (
            <HitCard key={h.chunk_id} hit={h} rank={idx + 1} query={query} kbId={kb.id} />
          ))
        )}
      </div>
    </div>
  );
};

const HitCard = ({
  hit,
  rank,
  query,
  kbId,
}: {
  hit: SearchHitItem;
  rank: number;
  query: string;
  kbId: import('@/core/types/api').EntityId;
}) => {
  const pct = Math.max(0, Math.min(100, Math.round(hit.score * 100)));
  return (
    <div className="rounded-lg border border-stone-200/70 bg-white p-3">
      <div className="mb-2 flex items-center justify-between text-[11px] text-stone-500">
        <div className="flex items-center gap-2">
          <span className="font-mono">#{rank}</span>
          <Link
            to={`/kbs/${kbId}/documents/${hit.doc_id}`}
            className="hover:underline"
          >
            {hit.document_title}
          </Link>
          <span className="text-stone-300">·</span>
          <span className="font-mono">seq {hit.seq}</span>
        </div>
        <ScoreBar pct={pct} />
      </div>
      <div
        className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-stone-800"
        dangerouslySetInnerHTML={{ __html: highlight(hit.content, query) }}
      />
    </div>
  );
};

const ScoreBar = ({ pct }: { pct: number }) => (
  <div className="flex items-center gap-2">
    <div className="h-1.5 w-20 overflow-hidden rounded-full bg-stone-100">
      <div
        className={cn(
          'h-full rounded-full',
          pct >= 70 ? 'bg-emerald-500' : pct >= 40 ? 'bg-amber-500' : 'bg-stone-400',
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
    <span className="w-10 text-right font-mono tnum text-[11px] text-stone-600">
      {pct}%
    </span>
  </div>
);

/** 在 content 里给 query 各 token 加 <mark>，转义 HTML 特殊字符 */
function highlight(content: string, query: string): string {
  const escaped = content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  const tokens = Array.from(
    new Set(
      query
        .toLowerCase()
        .split(/[\s,。，；;.!?！？]+/)
        .filter(t => t.length >= 2),
    ),
  );
  if (tokens.length === 0) return escaped;
  // 按长度倒序，避免短 token 抢先匹配
  tokens.sort((a, b) => b.length - a.length);
  const pattern = new RegExp(
    `(${tokens.map(escapeRegex).join('|')})`,
    'gi',
  );
  return escaped.replace(
    pattern,
    '<mark class="bg-amber-100 rounded px-0.5 text-stone-900">$1</mark>',
  );
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

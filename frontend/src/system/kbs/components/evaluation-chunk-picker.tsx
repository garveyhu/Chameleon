/** 评测「期望片段」选择器
 *
 * 解决「填 chunk_id」无从下手的问题：搜索本 KB，点选「这条查询的正确答案应包含哪些片段」，
 * 内部记 chunk_id、用户只看内容。返回选中的片段（含 id + 内容快照供展示）。
 */

import { useMutation } from '@tanstack/react-query';
import { Check, Search, X } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { cn } from '@/core/lib/cn';
import type { EntityId } from '@/core/types/api';
import { documentApi } from '@/system/kbs/services/document';
import type { SearchHitItem } from '@/system/kbs/types/kb';

/** 选中的期望片段：id 入库，content/title 仅前端展示 */
export interface ExpectedChunk {
  chunk_id: EntityId;
  content: string;
  document_title: string;
}

interface Props {
  open: boolean;
  kbId: EntityId;
  /** 打开时的默认搜索词（一般 = 该查询本身） */
  defaultQuery: string;
  initial: ExpectedChunk[];
  onConfirm: (selected: ExpectedChunk[]) => void;
  onClose: () => void;
}

export const EvaluationChunkPicker = ({
  open,
  kbId,
  defaultQuery,
  initial,
  onConfirm,
  onClose,
}: Props) => {
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<SearchHitItem[]>([]);
  const [picked, setPicked] = useState<Map<string, ExpectedChunk>>(new Map());

  // 打开瞬间用初始选中 + 默认搜索词重置（render 期 reset-on-open，避免 effect 里 setState）
  const [wasOpen, setWasOpen] = useState(false);
  if (open && !wasOpen) {
    setWasOpen(true);
    setQ(defaultQuery);
    setHits([]);
    setPicked(new Map(initial.map(c => [String(c.chunk_id), c])));
  } else if (!open && wasOpen) {
    setWasOpen(false);
  }

  const searchMut = useMutation({
    mutationFn: () =>
      documentApi.search(kbId, { query: q.trim(), top_k: 20, mode: 'hybrid' }),
    onSuccess: setHits,
  });

  const toggle = (h: SearchHitItem) => {
    const key = String(h.chunk_id);
    setPicked(prev => {
      const next = new Map(prev);
      if (next.has(key)) next.delete(key);
      else
        next.set(key, {
          chunk_id: h.chunk_id,
          content: h.content,
          document_title: h.document_title,
        });
      return next;
    });
  };

  const removeChip = (key: string) =>
    setPicked(prev => {
      const next = new Map(prev);
      next.delete(key);
      return next;
    });

  const selected = [...picked.values()];

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="lg">
        <ModalHeader>
          <ModalTitle>选择期望命中的片段</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-3">
          <p className="text-[11.5px] text-stone-500">
            搜索本知识库，勾选「这条查询的正确答案应当命中」的片段。评测会用它算命中率。
          </p>

          {/* 已选 chips */}
          {selected.length > 0 && (
            <div className="flex flex-wrap gap-1.5 rounded-md bg-stone-50 p-2">
              {selected.map(c => (
                <span
                  key={String(c.chunk_id)}
                  className="inline-flex max-w-[260px] items-center gap-1 rounded bg-amber-100 px-1.5 py-0.5 text-[11px] text-amber-800"
                >
                  <span className="truncate">{c.content || `#${c.chunk_id}`}</span>
                  <button
                    type="button"
                    onClick={() => removeChip(String(c.chunk_id))}
                    className="shrink-0 hover:text-amber-950"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          )}

          {/* 搜索 */}
          <div className="flex gap-2">
            <Input
              value={q}
              onChange={e => setQ(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && q.trim() && searchMut.mutate()}
              placeholder="搜索片段…"
              className="h-8 text-[12.5px]"
            />
            <Button
              size="sm"
              onClick={() => searchMut.mutate()}
              disabled={!q.trim() || searchMut.isPending}
            >
              <Search className="mr-1 h-3.5 w-3.5" />
              {searchMut.isPending ? '搜索中…' : '搜索'}
            </Button>
          </div>

          {/* 结果 */}
          <div className="max-h-[340px] space-y-1.5 overflow-y-auto">
            {hits.length === 0 ? (
              <div className="py-10 text-center text-[12px] text-stone-400">
                {searchMut.isSuccess ? '没有搜到片段' : '输入关键词后搜索，点选相关片段'}
              </div>
            ) : (
              hits.map(h => {
                const on = picked.has(String(h.chunk_id));
                return (
                  <button
                    key={String(h.chunk_id)}
                    type="button"
                    onClick={() => toggle(h)}
                    className={cn(
                      'flex w-full items-start gap-2 rounded-lg border p-2.5 text-left transition',
                      on
                        ? 'border-amber-300 bg-amber-50/60'
                        : 'border-stone-200/70 bg-white hover:border-amber-200',
                    )}
                  >
                    <span
                      className={cn(
                        'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border',
                        on ? 'border-amber-500 bg-amber-500 text-white' : 'border-stone-300',
                      )}
                    >
                      {on && <Check className="h-3 w-3" strokeWidth={3} />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="mb-0.5 flex items-center gap-2 text-[10.5px] text-stone-400">
                        <span className="truncate">{h.document_title}</span>
                        <span className="ml-auto shrink-0 font-mono">seq {h.seq}</span>
                      </div>
                      <div className="line-clamp-2 text-[12px] leading-snug text-stone-700">
                        {h.content}
                      </div>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button onClick={() => onConfirm(selected)}>确定（{selected.length} 条）</Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

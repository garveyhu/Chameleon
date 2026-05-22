/** Chunk 卡片 —— 卡片墙单元 + 双击编辑 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Check, Copy, Pencil, X } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/core/components/ui/button';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import type { ChunkItem } from '@/system/kbs/types/kb';

interface Props {
  chunk: ChunkItem;
  /** 编辑保存的回调；暂未提供后端编辑端点时设 undefined → 卡片隐藏编辑入口 */
  onSave?: (chunkId: number, content: string) => Promise<void>;
}

const MAX_PREVIEW_CHARS = 480;

export const ChunkCard = ({ chunk, onSave }: Props) => {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(chunk.content);
  const [expanded, setExpanded] = useState(false);
  const qc = useQueryClient();

  const saveMut = useMutation({
    mutationFn: async () => {
      if (!onSave) return;
      await onSave(chunk.id, draft);
    },
    onSuccess: () => {
      toast.success('已保存（将触发 re-embed）');
      setEditing(false);
      qc.invalidateQueries({ queryKey: ['kb-doc-chunks'] });
    },
    onError: () => toast.error('保存失败'),
  });

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(chunk.content);
      toast.success('已复制');
    } catch {
      toast.error('复制失败');
    }
  };

  const content = chunk.content || '';
  const needTruncate = !expanded && content.length > MAX_PREVIEW_CHARS;
  const display = needTruncate
    ? `${content.slice(0, MAX_PREVIEW_CHARS)}…`
    : content;

  return (
    <div
      className={cn(
        'group rounded-lg border border-stone-200/70 bg-white p-3 transition',
        'hover:border-amber-300 hover:shadow-sm',
      )}
      onDoubleClick={() => onSave && !editing && setEditing(true)}
    >
      <div className="mb-2 flex items-center justify-between text-[11px] text-stone-500">
        <span className="font-mono">
          #{chunk.seq}
          {chunk.token_count != null && (
            <span className="ml-2 tnum">{chunk.token_count} tokens</span>
          )}
        </span>
        <div className="flex gap-1 opacity-0 transition group-hover:opacity-100">
          <button
            type="button"
            title="复制"
            onClick={copy}
            className="rounded p-0.5 hover:bg-stone-100"
          >
            <Copy className="h-3 w-3" />
          </button>
          {onSave && !editing && (
            <button
              type="button"
              title="编辑"
              onClick={() => setEditing(true)}
              className="rounded p-0.5 hover:bg-stone-100"
            >
              <Pencil className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>
      {editing ? (
        <div className="space-y-2">
          <Textarea
            value={draft}
            onChange={e => setDraft(e.target.value)}
            rows={8}
            className="text-[12.5px] font-mono"
          />
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setEditing(false);
                setDraft(chunk.content);
              }}
              disabled={saveMut.isPending}
            >
              <X className="mr-1 h-3 w-3" /> 取消
            </Button>
            <Button
              size="sm"
              onClick={() => saveMut.mutate()}
              disabled={saveMut.isPending || draft === chunk.content}
            >
              <Check className="mr-1 h-3 w-3" /> 保存
            </Button>
          </div>
        </div>
      ) : (
        <>
          <div className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-stone-800">
            {display}
          </div>
          {needTruncate && (
            <button
              type="button"
              onClick={() => setExpanded(true)}
              className="mt-1 text-[11px] text-amber-700 hover:underline"
            >
              展开（共 {content.length} 字）
            </button>
          )}
        </>
      )}
    </div>
  );
};

/** Chunk 卡片 —— 段落级交互：查看 / 编辑(重嵌) / 启停 / 删除（Dify 段落管理） */
import { useState } from 'react';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Check, Copy, Eye, EyeOff, Pencil, Trash2, X } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { confirm } from '@/core/lib/confirm';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { documentApi } from '@/system/kbs/services/document';
import type { ChunkItem } from '@/system/kbs/types/kb';

interface Props {
  chunk: ChunkItem;
  kbId: EntityId;
  docId: EntityId;
}

const MAX_PREVIEW_CHARS = 480;

export const ChunkCard = ({ chunk, kbId, docId }: Props) => {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(chunk.content);
  const [expanded, setExpanded] = useState(false);
  const qc = useQueryClient();

  const invalidate = () => qc.invalidateQueries({ queryKey: ['kb-doc-chunks', kbId, docId] });

  const saveMut = useMutation({
    mutationFn: () => documentApi.updateChunk(kbId, docId, chunk.id, { content: draft }),
    onSuccess: () => {
      toast.success('已保存并重嵌');
      setEditing(false);
      invalidate();
    },
    onError: e => toast.error(`保存失败：${(e as Error).message}`),
  });

  const toggleMut = useMutation({
    mutationFn: () => documentApi.updateChunk(kbId, docId, chunk.id, { enabled: !chunk.enabled }),
    onSuccess: () => {
      toast.success(chunk.enabled ? '已停用（不参与检索）' : '已启用');
      invalidate();
    },
    onError: e => toast.error(`操作失败：${(e as Error).message}`),
  });

  const deleteMut = useMutation({
    mutationFn: () => documentApi.deleteChunk(kbId, docId, chunk.id),
    onSuccess: () => {
      toast.success('已删除');
      invalidate();
    },
    onError: e => toast.error(`删除失败：${(e as Error).message}`),
  });

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(chunk.content);
      toast.success('已复制');
    } catch {
      toast.error('复制失败');
    }
  };

  const onDelete = async () => {
    if (await confirm({ title: '删除该切块？', description: '删除后不可恢复。', danger: true })) {
      deleteMut.mutate();
    }
  };

  const content = chunk.content || '';
  const needTruncate = !expanded && content.length > MAX_PREVIEW_CHARS;
  const display = needTruncate ? `${content.slice(0, MAX_PREVIEW_CHARS)}…` : content;

  return (
    <div
      className={cn(
        'group rounded-lg border border-stone-200/70 bg-white p-3 transition hover:border-amber-300 hover:shadow-sm',
        !chunk.enabled && 'opacity-55',
      )}
      onDoubleClick={() => !editing && setEditing(true)}
    >
      <div className="mb-2 flex items-center justify-between text-[11px] text-stone-500">
        <span className="flex items-center gap-2 font-mono">
          #{chunk.seq}
          {chunk.token_count != null && <span className="tnum">{chunk.token_count} tok</span>}
          {chunk.hit_count > 0 && (
            <span className="tnum text-emerald-600">命中 {chunk.hit_count}</span>
          )}
          {!chunk.enabled && <span className="text-stone-400">· 已停用</span>}
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
          {!editing && (
            <button
              type="button"
              title="编辑"
              onClick={() => setEditing(true)}
              className="rounded p-0.5 hover:bg-stone-100"
            >
              <Pencil className="h-3 w-3" />
            </button>
          )}
          <button
            type="button"
            title={chunk.enabled ? '停用' : '启用'}
            onClick={() => toggleMut.mutate()}
            disabled={toggleMut.isPending}
            className="rounded p-0.5 hover:bg-stone-100"
          >
            {chunk.enabled ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
          </button>
          <button
            type="button"
            title="删除"
            onClick={onDelete}
            className="rounded p-0.5 text-stone-400 hover:bg-rose-50 hover:text-rose-500"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      </div>

      {editing ? (
        <div className="space-y-2">
          <Textarea
            value={draft}
            onChange={e => setDraft(e.target.value)}
            rows={8}
            className="font-mono text-[12.5px]"
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
              disabled={saveMut.isPending || draft === chunk.content || !draft.trim()}
            >
              <Check className="mr-1 h-3 w-3" /> 保存
            </Button>
          </div>
        </div>
      ) : (
        <>
          <div className="text-[12.5px] leading-relaxed whitespace-pre-wrap text-stone-800">
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
          {chunk.keywords && chunk.keywords.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {chunk.keywords.map(k => (
                <span
                  key={k}
                  className="rounded bg-stone-100 px-1.5 py-0.5 text-[10px] text-stone-500"
                >
                  {k}
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
};

/** 对话详情页 —— 树视图 + 分支切换器 + regenerate/edit-and-resend（P21.4 PR #67+#68） */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  Bot,
  Edit3,
  Loader2,
  RefreshCw,
  User2,
  Wrench,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { SectionCard } from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { BranchSwitcher } from '@/system/conversations/components/branch-switcher';
import {
  useMessageTree,
  type BranchSelections,
} from '@/system/conversations/hooks/use-message-tree';
import { conversationApi } from '@/system/conversations/services/conversation';
import type {
  BranchRenderItem,
  MessageItem,
} from '@/system/conversations/types/message-tree';

export const ConversationDetailPage = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const sid = sessionId ?? '';

  const convQ = useQuery({
    queryKey: ['conversations', sid],
    queryFn: () => conversationApi.get(sid),
    enabled: !!sid,
  });

  const msgsQ = useQuery({
    queryKey: ['conversations', sid, 'messages'],
    queryFn: () => conversationApi.listMessages(sid),
    enabled: !!sid,
  });

  const [selections, setSelections] = useState<BranchSelections>({});
  const { visible, tree, defaultSelections } = useMessageTree(
    msgsQ.data?.items,
    selections,
  );

  const qc = useQueryClient();
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['conversations', sid, 'messages'] });
  };

  // 用户切支 → merge selections（保留显式选过的，覆盖 default）
  const onSwitchBranch = (parentKey: string, nextId: EntityId) => {
    setSelections(prev => ({ ...prev, [parentKey]: nextId }));
  };

  const regenMut = useMutation({
    mutationFn: (mid: EntityId) => conversationApi.regenerate(sid, mid),
    onSuccess: (m: MessageItem) => {
      toast.success('已生成新分支');
      // 自动切到新分支：parent_message_id → new_msg.id
      if (m.parent_message_id != null) {
        setSelections(prev => ({
          ...prev,
          [String(m.parent_message_id)]: m.id,
        }));
      }
      refresh();
    },
    onError: e => toast.error('regenerate 失败：' + (e as Error).message),
  });

  const editMut = useMutation({
    mutationFn: (p: { mid: EntityId; text: string }) =>
      conversationApi.editAndResend(sid, p.mid, p.text),
    onSuccess: (newAssistant: MessageItem) => {
      toast.success('已生成新分支');
      // 新 assistant 的 parent 是新 user；切到新 user
      if (newAssistant.parent_message_id != null) {
        // new_user.parent_message_id = old user 的 parent → selections 切支
        // 简化：refresh 后由 useMessageTree default 自动选最新（seq desc）
      }
      refresh();
      setEditingId(null);
    },
    onError: e => toast.error('编辑失败：' + (e as Error).message),
  });

  const [editingId, setEditingId] = useState<EntityId | null>(null);
  const [editText, setEditText] = useState('');

  const branchInfo = useMemo(() => {
    let totalBranches = 0;
    let alternatives = 0;
    walkTree(tree, n => {
      if (n.children.length > 1) {
        totalBranches += 1;
        alternatives += n.children.length;
      }
    });
    return { totalBranches, alternatives };
  }, [tree]);

  if (!sid) {
    return (
      <SectionCard>
        <div className="p-6 text-sm text-stone-500">非法的 session_id</div>
      </SectionCard>
    );
  }

  return (
    <div className="space-y-3">
      <header className="flex items-center gap-3">
        <Link
          to="/conversations"
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12.5px] text-stone-500 hover:bg-stone-100 hover:text-stone-800"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> 对话
        </Link>
        <span className="text-stone-300">/</span>
        {convQ.isLoading ? (
          <span className="text-[12.5px] text-stone-400">加载中…</span>
        ) : convQ.data ? (
          <div className="flex flex-1 items-baseline gap-2">
            <span className="text-[15px] font-medium text-stone-900">
              {convQ.data.title || '(无标题)'}
            </span>
            <span className="font-mono text-[11px] text-stone-500">
              {convQ.data.session_id}
            </span>
            <span className="ml-auto" />
            {branchInfo.totalBranches > 0 && (
              <span className="rounded bg-fuchsia-50 px-1.5 py-0.5 text-[10.5px] text-fuchsia-700">
                {branchInfo.totalBranches} 个分叉点 · {branchInfo.alternatives} 条分支
              </span>
            )}
          </div>
        ) : (
          <span className="text-[12.5px] text-stone-400">未找到</span>
        )}
      </header>

      <SectionCard className="!p-0">
        <div className="divide-y divide-stone-100">
          {visible.map(item => (
            <MessageRow
              key={String(item.message.id)}
              item={item}
              onSwitchBranch={onSwitchBranch}
              isEditing={String(editingId) === String(item.message.id)}
              editText={editText}
              setEditText={setEditText}
              startEdit={() => {
                setEditingId(item.message.id);
                setEditText(item.message.content);
              }}
              cancelEdit={() => setEditingId(null)}
              onRegenerate={() => regenMut.mutate(item.message.id)}
              onSubmitEdit={() =>
                editMut.mutate({ mid: item.message.id, text: editText })
              }
              regenPending={regenMut.isPending}
              editPending={editMut.isPending}
            />
          ))}
          {msgsQ.data && visible.length === 0 && (
            <div className="px-3 py-12 text-center text-[12px] text-stone-400">
              暂无消息
            </div>
          )}
          {msgsQ.isLoading && (
            <div className="px-3 py-12 text-center text-[12px] text-stone-400">
              加载消息中…
            </div>
          )}
        </div>
      </SectionCard>
    </div>
  );
};

const ROLE_META: Record<
  string,
  { label: string; icon: typeof Bot; color: string; bg: string }
> = {
  user: { label: 'USER', icon: User2, color: 'text-blue-700', bg: 'bg-blue-50' },
  assistant: {
    label: 'ASSISTANT',
    icon: Bot,
    color: 'text-emerald-700',
    bg: 'bg-emerald-50',
  },
  system: {
    label: 'SYSTEM',
    icon: Wrench,
    color: 'text-stone-700',
    bg: 'bg-stone-50',
  },
  tool: {
    label: 'TOOL',
    icon: Wrench,
    color: 'text-amber-700',
    bg: 'bg-amber-50',
  },
};

interface MessageRowProps {
  item: BranchRenderItem;
  onSwitchBranch: (parentKey: string, nextId: EntityId) => void;
  isEditing: boolean;
  editText: string;
  setEditText: (s: string) => void;
  startEdit: () => void;
  cancelEdit: () => void;
  onRegenerate: () => void;
  onSubmitEdit: () => void;
  regenPending: boolean;
  editPending: boolean;
}

const MessageRow = ({
  item,
  onSwitchBranch,
  isEditing,
  editText,
  setEditText,
  startEdit,
  cancelEdit,
  onRegenerate,
  onSubmitEdit,
  regenPending,
  editPending,
}: MessageRowProps) => {
  const meta =
    ROLE_META[item.message.role] ?? {
      label: item.message.role.toUpperCase(),
      icon: User2,
      color: 'text-stone-700',
      bg: 'bg-stone-50',
    };
  const parentKey =
    item.message.parent_message_id == null
      ? '__root__'
      : String(item.message.parent_message_id);

  const role = item.message.role;
  return (
    <div className="group px-3 py-3">
      <div className="mb-1 flex items-center gap-2 text-[10.5px]">
        <span
          className={cn(
            'inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-mono',
            meta.bg,
            meta.color,
          )}
        >
          <meta.icon className="h-3 w-3" />
          {meta.label}
        </span>
        <span className="font-mono text-[10.5px] text-stone-400">
          #{item.message.seq}
        </span>
        <BranchSwitcher
          siblingIds={item.siblingIds}
          currentId={item.message.id}
          onSelect={next => onSwitchBranch(parentKey, next)}
        />
        <span className="ml-auto inline-flex items-center gap-1 opacity-0 transition group-hover:opacity-100">
          {role === 'user' && !isEditing && (
            <button
              type="button"
              onClick={startEdit}
              className="rounded p-1 text-stone-500 hover:bg-stone-100 hover:text-stone-800"
              title="编辑 + 重发（创建新分支）"
            >
              <Edit3 className="h-3 w-3" />
            </button>
          )}
          {role === 'assistant' && (
            <button
              type="button"
              onClick={onRegenerate}
              disabled={regenPending}
              className="rounded p-1 text-stone-500 hover:bg-stone-100 hover:text-stone-800 disabled:opacity-40"
              title="重新生成（创建新分支）"
            >
              {regenPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <RefreshCw className="h-3 w-3" />
              )}
            </button>
          )}
        </span>
        <span className="text-[10.5px] text-stone-400">
          {formatDateTime(item.message.created_at)}
        </span>
      </div>
      {isEditing ? (
        <div className="space-y-2">
          <Textarea
            value={editText}
            onChange={e => setEditText(e.target.value)}
            rows={4}
            className="font-mono text-[12.5px]"
          />
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={cancelEdit}>
              取消
            </Button>
            <Button
              size="sm"
              disabled={!editText.trim() || editPending}
              onClick={onSubmitEdit}
            >
              {editPending && (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              )}
              发送（新分支）
            </Button>
          </div>
        </div>
      ) : (
        <>
          <div className="whitespace-pre-wrap text-[13px] leading-relaxed text-stone-800">
            {item.message.content}
          </div>
          {item.message.usage && (
            <div className="mt-1 font-mono text-[10.5px] text-stone-400">
              usage · in={String(item.message.usage.prompt_tokens ?? '?')} · out={String(item.message.usage.completion_tokens ?? '?')}
            </div>
          )}
        </>
      )}
    </div>
  );
};

function walkTree(
  nodes: { children: { children: unknown[] }[] }[],
  fn: (n: { children: unknown[] }) => void,
) {
  // 仅做形态遍历；类型放宽以避免循环依赖
  for (const n of nodes as unknown as Array<{
    children: Array<{ children: unknown[] }>;
  }>) {
    fn(n);
    walkTree(n.children as never, fn);
  }
}

// 显式 _ 避开 lint 提醒：MessageItem 仅作类型导出参考
const _typeRef: MessageItem | null = null;
void _typeRef;

/** 单条消息 hover 上的 Actions 工具条
 *
 * 设计：
 * - assistant 消息：copy / regenerate / 👍 / 👎 / delete
 * - user 消息：copy / edit / delete
 * - 流式中只显 copy，避免误操作
 * - 反馈状态本地持久（feedback 字段），异步打 /v1/admin/scores
 */

import {
  Check,
  Copy,
  Pencil,
  RefreshCw,
  ThumbsDown,
  ThumbsUp,
  Trash2,
} from 'lucide-react';
import { useState } from 'react';

import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import { scoreApi } from '@/system/call_logs/services/call-log';
import type { PlaygroundMessage } from '@/system/playground/types/playground';

export interface MessageActionsProps {
  msg: PlaygroundMessage;
  onCopy?: () => void;
  onEdit?: () => void;
  onRegenerate?: () => void;
  onDelete?: () => void;
  onFeedbackChange?: (value: 1 | -1 | null) => void;
}

export const MessageActions = ({
  msg,
  onCopy,
  onEdit,
  onRegenerate,
  onDelete,
  onFeedbackChange,
}: MessageActionsProps) => {
  const [copied, setCopied] = useState(false);
  const isUser = msg.role === 'user';
  const isAssistant = msg.role === 'assistant';
  const isStreaming = msg.status === 'streaming';
  const isFailed = msg.status === 'failed';

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(msg.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
      onCopy?.();
    } catch {
      toast.error('复制失败：浏览器无 clipboard 权限');
    }
  };

  const handleFeedback = (positive: boolean) => {
    if (!msg.requestId) {
      toast.error('该消息没有 request_id，无法反馈');
      return;
    }
    const target: 1 | -1 = positive ? 1 : -1;
    const next: 1 | -1 | null = msg.feedback === target ? null : target;
    onFeedbackChange?.(next);
    if (next !== null) {
      // append-only：每次新点都写一条 score
      void scoreApi
        .create({
          call_log_id: msg.requestId,
          trace_id: msg.requestId,
          name: 'thumbs',
          value: next,
          data_type: 'numeric',
          source: 'annotation',
        })
        .catch(() => toast.error('反馈写入失败'));
    }
  };

  return (
    <div
      className={cn(
        'pointer-events-auto flex items-center gap-0.5 rounded-md border border-stone-200/70 bg-white/90 p-0.5 shadow-sm backdrop-blur transition',
        'opacity-0 group-hover:opacity-100 focus-within:opacity-100',
      )}
    >
      <ActionBtn title={copied ? '已复制' : '复制'} onClick={handleCopy}>
        {copied ? (
          <Check className="h-3 w-3 text-emerald-600" />
        ) : (
          <Copy className="h-3 w-3" />
        )}
      </ActionBtn>

      {isAssistant && !isStreaming && (
        <>
          <ActionBtn
            title="重新生成"
            onClick={onRegenerate}
            disabled={!onRegenerate}
          >
            <RefreshCw className="h-3 w-3" />
          </ActionBtn>
          {/* 反馈仅在有 requestId（=trace_id）时可用；playground 不写 call_log 时直接隐藏 */}
          {msg.requestId && (
            <>
              <ActionBtn
                title={msg.feedback === 1 ? '取消 👍' : '👍 有帮助'}
                onClick={() => handleFeedback(true)}
                active={msg.feedback === 1}
              >
                <ThumbsUp className="h-3 w-3" />
              </ActionBtn>
              <ActionBtn
                title={msg.feedback === -1 ? '取消 👎' : '👎 没帮助'}
                onClick={() => handleFeedback(false)}
                active={msg.feedback === -1}
              >
                <ThumbsDown className="h-3 w-3" />
              </ActionBtn>
            </>
          )}
        </>
      )}

      {isUser && !isStreaming && (
        <ActionBtn title="编辑并重发" onClick={onEdit} disabled={!onEdit}>
          <Pencil className="h-3 w-3" />
        </ActionBtn>
      )}

      {!isStreaming && (
        <ActionBtn
          title={isFailed ? '删除失败消息' : '删除'}
          onClick={onDelete}
          danger
          disabled={!onDelete}
        >
          <Trash2 className="h-3 w-3" />
        </ActionBtn>
      )}
    </div>
  );
};

const ActionBtn = ({
  title,
  onClick,
  children,
  active,
  danger,
  disabled,
}: {
  title: string;
  onClick?: () => void;
  children: React.ReactNode;
  active?: boolean;
  danger?: boolean;
  disabled?: boolean;
}) => (
  <button
    type="button"
    title={title}
    onClick={onClick}
    disabled={disabled}
    className={cn(
      'rounded px-1 py-1 text-stone-500 transition disabled:cursor-not-allowed disabled:opacity-40',
      !disabled &&
        (danger
          ? 'hover:bg-rose-50 hover:text-rose-600'
          : 'hover:bg-stone-100 hover:text-stone-800'),
      active &&
        !disabled &&
        (danger
          ? 'bg-rose-100 text-rose-700'
          : 'bg-amber-100 text-amber-800'),
    )}
  >
    {children}
  </button>
);

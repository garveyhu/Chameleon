/** 单条消息的 Actions 工具条（公共组件）
 *
 * 13 actions：copy / edit / regenerate / delete / 👍 / 👎 / branching /
 * translate / continueGen / tts / export / share / pin。
 *
 * - 主操作（copy / edit / regenerate / 👍 / 👎）内联在 hover 条上
 * - 次操作收进 ⋯ 下拉菜单；translate 在配了语言列表时渲染为子菜单
 * - copy / tts / export / share 自带默认实现，消费方可用 handler 覆盖
 * - 适用性 / 分组逻辑见 resolve-actions.ts
 *
 * 跨页复用：playground / conversations / widget 各自把消息映射为 ChatActionMessage。
 */

import {
  ArrowDownFromLine,
  Check,
  Copy,
  Download,
  Languages,
  type LucideIcon,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  RefreshCw,
  Share2,
  Split,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  Volume2,
  VolumeX,
} from 'lucide-react';
import { useState } from 'react';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/core/components/ui/dropdown-menu';
import type {
  ChatActionMessage,
  MessageActionHandlers,
  MessageActionKey,
  TranslateLanguage,
} from '@/core/components/chat/message-actions.types';
import { resolveActions } from '@/core/components/chat/resolve-actions';
import { useSpeech } from '@/core/components/chat/use-speech';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';

export interface MessageActionsProps {
  msg: ChatActionMessage;
  handlers?: MessageActionHandlers;
  /** 配置后 translate 渲染为语言子菜单；否则点击直接 onTranslate() */
  translateLanguages?: TranslateLanguage[];
  /** 强制隐藏某些 action（即便适用 / 有 handler） */
  hidden?: MessageActionKey[];
  className?: string;
}

const ICON: Record<MessageActionKey, LucideIcon> = {
  copy: Copy,
  edit: Pencil,
  regenerate: RefreshCw,
  delete: Trash2,
  thumbsUp: ThumbsUp,
  thumbsDown: ThumbsDown,
  branching: Split,
  translate: Languages,
  continueGen: ArrowDownFromLine,
  tts: Volume2,
  export: Download,
  share: Share2,
  pin: Pin,
};

const LABEL: Record<MessageActionKey, string> = {
  copy: '复制',
  edit: '编辑',
  regenerate: '重新生成',
  delete: '删除',
  thumbsUp: '👍 有帮助',
  thumbsDown: '👎 没帮助',
  branching: '从此分叉',
  translate: '翻译',
  continueGen: '继续生成',
  tts: '朗读',
  export: '导出 Markdown',
  share: '复制分享片段',
  pin: '置顶',
};

export const MessageActions = ({
  msg,
  handlers = {},
  translateLanguages,
  hidden,
  className,
}: MessageActionsProps) => {
  const [copied, setCopied] = useState(false);
  const speech = useSpeech();
  const hiddenSet = new Set<MessageActionKey>(hidden ?? []);
  const { primary, more } = resolveActions(msg, handlers, hiddenSet);

  const runCopy = async () => {
    try {
      await navigator.clipboard.writeText(msg.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
      handlers.onCopy?.();
    } catch {
      toast.error('复制失败：浏览器无 clipboard 权限');
    }
  };

  const runFeedback = (positive: boolean) => {
    const target: 1 | -1 = positive ? 1 : -1;
    const next: 1 | -1 | null = msg.feedback === target ? null : target;
    handlers.onFeedback?.(next);
  };

  const runTts = () => {
    if (handlers.onTts) {
      handlers.onTts();
      return;
    }
    if (!speech.supported) {
      toast.error('当前浏览器不支持语音朗读');
      return;
    }
    speech.toggle(msg.content);
  };

  const runExport = () => {
    if (handlers.onExport) {
      handlers.onExport();
      return;
    }
    downloadText(
      `## ${msg.role}\n\n${msg.content}\n`,
      `message-${msg.id}.md`,
    );
  };

  const runShare = async () => {
    if (handlers.onShare) {
      handlers.onShare();
      return;
    }
    try {
      await navigator.clipboard.writeText(`> ${msg.role}\n\n${msg.content}`);
      toast.success('已复制分享片段到剪贴板');
    } catch {
      toast.error('复制失败：浏览器无 clipboard 权限');
    }
  };

  /** 把 action key 映射到点击行为 */
  const invoke = (key: MessageActionKey) => {
    switch (key) {
      case 'copy':
        return void runCopy();
      case 'edit':
        return handlers.onEdit?.();
      case 'regenerate':
        return handlers.onRegenerate?.();
      case 'delete':
        return handlers.onDelete?.();
      case 'thumbsUp':
        return runFeedback(true);
      case 'thumbsDown':
        return runFeedback(false);
      case 'branching':
        return handlers.onBranch?.();
      case 'translate':
        return handlers.onTranslate?.();
      case 'continueGen':
        return handlers.onContinue?.();
      case 'tts':
        return runTts();
      case 'export':
        return runExport();
      case 'share':
        return void runShare();
      case 'pin':
        return handlers.onPin?.(!msg.pinned);
    }
  };

  const renderIcon = (key: MessageActionKey) => {
    if (key === 'copy' && copied)
      return <Check className="h-3 w-3 text-emerald-600" />;
    if (key === 'tts' && !handlers.onTts && speech.speaking)
      return <VolumeX className="h-3 w-3" />;
    if (key === 'pin' && msg.pinned) return <PinOff className="h-3 w-3" />;
    const Icon = ICON[key];
    return <Icon className="h-3 w-3" />;
  };

  const isActive = (key: MessageActionKey) =>
    (key === 'thumbsUp' && msg.feedback === 1) ||
    (key === 'thumbsDown' && msg.feedback === -1) ||
    (key === 'pin' && !!msg.pinned) ||
    (key === 'tts' && !handlers.onTts && speech.speaking);

  if (primary.length === 0 && more.length === 0) return null;

  return (
    <div
      className={cn(
        'pointer-events-auto flex items-center gap-0.5 rounded-md border border-stone-200/70 bg-white/90 p-0.5 shadow-sm backdrop-blur transition',
        'opacity-0 group-hover:opacity-100 focus-within:opacity-100',
        className,
      )}
    >
      {primary.map(key => (
        <ActionBtn
          key={key}
          title={titleOf(key, msg)}
          onClick={() => invoke(key)}
          active={isActive(key)}
          danger={key === 'delete'}
        >
          {renderIcon(key)}
        </ActionBtn>
      ))}

      {more.length > 0 && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              title="更多"
              className="rounded px-1 py-1 text-stone-500 transition hover:bg-stone-100 hover:text-stone-800"
            >
              <MoreHorizontal className="h-3 w-3" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-[9rem]">
            {more.map(key => {
              if (
                key === 'translate' &&
                translateLanguages &&
                translateLanguages.length > 0
              ) {
                return (
                  <DropdownMenuSub key={key}>
                    <DropdownMenuSubTrigger>
                      <MenuRow icon={renderIcon(key)} label={LABEL.translate} />
                    </DropdownMenuSubTrigger>
                    <DropdownMenuSubContent>
                      {translateLanguages.map(lang => (
                        <DropdownMenuItem
                          key={lang.code}
                          onSelect={() => handlers.onTranslate?.(lang.code)}
                        >
                          {lang.label}
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuSubContent>
                  </DropdownMenuSub>
                );
              }
              if (key === 'delete') {
                return (
                  <div key={key}>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      className="text-rose-600 hover:bg-rose-50 hover:text-rose-700 focus:bg-rose-50 focus:text-rose-700"
                      onSelect={() => invoke(key)}
                    >
                      <MenuRow icon={renderIcon(key)} label={LABEL.delete} />
                    </DropdownMenuItem>
                  </div>
                );
              }
              return (
                <DropdownMenuItem
                  key={key}
                  className={cn(isActive(key) && 'text-amber-700')}
                  onSelect={() => invoke(key)}
                >
                  <MenuRow icon={renderIcon(key)} label={labelOf(key, msg)} />
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
};

const MenuRow = ({
  icon,
  label,
}: {
  icon: React.ReactNode;
  label: string;
}) => (
  <span className="flex items-center gap-2">
    <span className="text-stone-500">{icon}</span>
    <span className="text-[12.5px]">{label}</span>
  </span>
);

function titleOf(key: MessageActionKey, msg: ChatActionMessage): string {
  if (key === 'thumbsUp') return msg.feedback === 1 ? '取消 👍' : LABEL.thumbsUp;
  if (key === 'thumbsDown')
    return msg.feedback === -1 ? '取消 👎' : LABEL.thumbsDown;
  return LABEL[key];
}

function labelOf(key: MessageActionKey, msg: ChatActionMessage): string {
  if (key === 'pin') return msg.pinned ? '取消置顶' : LABEL.pin;
  if (key === 'tts') return LABEL.tts;
  return LABEL[key];
}

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
        (danger ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-800'),
    )}
  >
    {children}
  </button>
);

function downloadText(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** 纯函数：根据消息形态 + handlers 决定渲染哪些 action、各落在主条还是 ⋯ 菜单 */

import type {
  ChatActionMessage,
  MessageActionHandlers,
  MessageActionKey,
} from '@/core/components/chat/message-actions.types';

/** 主条内联（hover 直出） */
const PRIMARY_ORDER: MessageActionKey[] = [
  'copy',
  'edit',
  'regenerate',
  'thumbsUp',
  'thumbsDown',
];

/** ⋯ 下拉菜单（次级动作） */
const MORE_ORDER: MessageActionKey[] = [
  'continueGen',
  'translate',
  'tts',
  'branching',
  'pin',
  'export',
  'share',
  'delete',
];

/** 组件自带默认实现，无 handler 也可渲染 */
const BUILT_IN: ReadonlySet<MessageActionKey> = new Set([
  'copy',
  'tts',
  'export',
  'share',
]);

const HANDLER_OF: Partial<Record<MessageActionKey, keyof MessageActionHandlers>> =
  {
    edit: 'onEdit',
    regenerate: 'onRegenerate',
    delete: 'onDelete',
    thumbsUp: 'onFeedback',
    thumbsDown: 'onFeedback',
    branching: 'onBranch',
    translate: 'onTranslate',
    continueGen: 'onContinue',
    pin: 'onPin',
  };

/** role / status 适用性 */
function appliesTo(key: MessageActionKey, msg: ChatActionMessage): boolean {
  const { role } = msg;
  switch (key) {
    case 'copy':
    case 'delete':
    case 'export':
    case 'share':
    case 'pin':
      return true;
    case 'translate':
    case 'tts':
      return role === 'user' || role === 'assistant';
    case 'edit':
      return role === 'user';
    case 'regenerate':
    case 'thumbsUp':
    case 'thumbsDown':
    case 'branching':
    case 'continueGen':
      return role === 'assistant';
    default:
      return false;
  }
}

function isAvailable(
  key: MessageActionKey,
  msg: ChatActionMessage,
  handlers: MessageActionHandlers,
  hidden: ReadonlySet<MessageActionKey>,
): boolean {
  if (hidden.has(key)) return false;
  if (!appliesTo(key, msg)) return false;
  if (BUILT_IN.has(key)) {
    // 内置：有覆盖 handler 时用 handler，否则用默认实现 —— 始终可渲染
    return true;
  }
  const handlerKey = HANDLER_OF[key];
  return handlerKey != null && handlers[handlerKey] != null;
}

export interface ResolvedActions {
  primary: MessageActionKey[];
  more: MessageActionKey[];
}

export function resolveActions(
  msg: ChatActionMessage,
  handlers: MessageActionHandlers,
  hidden: ReadonlySet<MessageActionKey>,
): ResolvedActions {
  // 流式中只留 copy，避免误操作
  if (msg.status === 'streaming') {
    return { primary: ['copy'], more: [] };
  }
  const pick = (order: MessageActionKey[]) =>
    order.filter(k => isAvailable(k, msg, handlers, hidden));
  return { primary: pick(PRIMARY_ORDER), more: pick(MORE_ORDER) };
}

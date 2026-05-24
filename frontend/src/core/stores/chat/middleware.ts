/** chat store —— 组装：state + actions slice，套 devtools（仅 dev） */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

import { type ChatActions, createChatActions } from '@/core/stores/chat/actions';
import { createInitialState } from '@/core/stores/chat/state';
import type { ChatState } from '@/core/stores/chat/state';

export type ChatStore = ChatState & ChatActions;

export const useChatStore = create<ChatStore>()(
  devtools(
    (...a) => ({
      ...createInitialState(),
      ...createChatActions(...a),
    }),
    { name: 'chat-store', enabled: import.meta.env.DEV },
  ),
);

import { get, post } from '@/core/lib/request';
import type { EntityId, PageResult } from '@/core/types/api';
import type {
  ConversationItem,
  MessageItem,
} from '@/system/conversations/types/message-tree';

export const conversationApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    agent_key?: string;
  }) =>
    get<PageResult<ConversationItem>>('/v1/sessions', { params }),
  get: (sessionId: string) =>
    get<ConversationItem>(`/v1/sessions/${sessionId}`),
  listMessages: (sessionId: string, params?: { page?: number; page_size?: number }) =>
    get<PageResult<MessageItem>>(
      `/v1/sessions/${sessionId}/messages`,
      { params: { page_size: 500, ...params } },
    ),

  // P21.4 PR #68：分支
  regenerate: (sessionId: string, messageId: EntityId) =>
    post<MessageItem>(
      `/v1/sessions/${sessionId}/messages/${messageId}/regenerate`,
    ),
  editAndResend: (
    sessionId: string,
    messageId: EntityId,
    newContent: string,
  ) =>
    post<MessageItem>(
      `/v1/sessions/${sessionId}/messages/${messageId}/edit-and-resend`,
      { new_content: newContent },
    ),
};

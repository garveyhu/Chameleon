/** chat store —— selectors slice：纯派生读取
 *
 * 组件用 `useChatStore(s => messagesOf(s, columnId))` 订阅，
 * 单列消息变化只触发该列重渲染（messages[id] 数组引用按列独立）。
 */

import type { ChatState } from '@/core/stores/chat/state';
import type { PlaygroundMessage } from '@/system/playground/types/playground';

const EMPTY: readonly PlaygroundMessage[] = Object.freeze([]);

export const messagesOf = (
  s: ChatState,
  columnId: string,
): PlaygroundMessage[] => (s.messages[columnId] ?? EMPTY) as PlaygroundMessage[];

export const isStreaming = (s: ChatState, columnId: string): boolean =>
  (s.messages[columnId] ?? EMPTY).some(m => m.status === 'streaming');

export const columnCount = (s: ChatState): number => s.columns.length;

export const paramsOf = (s: ChatState, columnId: string) =>
  s.columns.find(c => c.id === columnId)?.params;

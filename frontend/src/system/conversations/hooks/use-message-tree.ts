/** useMessageTree —— 把扁平 messages 按 parent_message_id 构树并展开成线性视图
 *
 * 算法：
 *   1. 按 parent_message_id 分组：children[parent_id] = sorted by seq
 *   2. roots = 那些 parent_message_id 为 null 的（线性主线的起点）
 *   3. 给每条消息计算 siblingCount / siblingIndex / siblingIds
 *   4. 按当前 selectedBranches（每个分叉点选 1 个）+ DFS 输出线性视图
 *
 * 红线（plan §2 P21）：regenerate 不破坏老分支 —— 老 message 不删，只是不在
 * 当前线性视图里渲染；切支后老分支恢复展示。
 */

import { useMemo } from 'react';

import type { EntityId } from '@/core/types/api';
import type {
  BranchRenderItem,
  MessageItem,
  MessageTreeNode,
} from '@/system/conversations/types/message-tree';

interface BranchSelections {
  /** parent_message_id (or 'root') → 选中的 child message id */
  [parentKey: string]: EntityId;
}

interface UseMessageTreeResult {
  /** 全树（diag 用） */
  tree: MessageTreeNode[];
  /** 按当前 selections 展开的线性视图 */
  visible: BranchRenderItem[];
  /** 默认 selections（最新分支优先；用于初始化 state） */
  defaultSelections: BranchSelections;
}

const ROOT_KEY = '__root__';

/**
 * 把扁平 messages 列表按 parent_message_id 组装成树 + 展开当前分支
 *
 * @param messages 扁平 messages 列表（任意顺序；内部按 seq 排序）
 * @param selections 用户当前选择的分支：{parent_id: selected_child_id}
 *                   未选择的分叉点用 defaultSelections（最新 seq 优先）
 */
export function useMessageTree(
  messages: MessageItem[] | undefined,
  selections: BranchSelections = {},
): UseMessageTreeResult {
  return useMemo(() => buildTree(messages ?? [], selections), [messages, selections]);
}

export function buildTree(
  messages: MessageItem[],
  selections: BranchSelections,
): UseMessageTreeResult {
  // 1) children map
  const childrenMap = new Map<string, MessageItem[]>();
  for (const m of messages) {
    const key = m.parent_message_id == null ? ROOT_KEY : String(m.parent_message_id);
    const arr = childrenMap.get(key) ?? [];
    arr.push(m);
    childrenMap.set(key, arr);
  }
  for (const arr of childrenMap.values()) {
    arr.sort((a, b) => a.seq - b.seq);
  }

  // 2) defaultSelections：每个分叉点选最新（seq 最大）的 child
  const defaultSelections: BranchSelections = {};
  for (const [parentKey, kids] of childrenMap.entries()) {
    if (kids.length > 1) {
      defaultSelections[parentKey] = kids[kids.length - 1].id;
    }
  }

  // 3) 构全树（diag 用，递归）
  const roots = childrenMap.get(ROOT_KEY) ?? [];
  const tree: MessageTreeNode[] = roots.map(r => buildNode(r, childrenMap));

  // 4) 展开当前分支：从 root 起 DFS，遇分叉看 selections / defaults
  const visible: BranchRenderItem[] = [];
  walkBranch(
    ROOT_KEY,
    childrenMap,
    { ...defaultSelections, ...selections },
    visible,
  );

  return { tree, visible, defaultSelections };
}

function buildNode(
  m: MessageItem,
  childrenMap: Map<string, MessageItem[]>,
): MessageTreeNode {
  const kids = childrenMap.get(String(m.id)) ?? [];
  return {
    message: m,
    children: kids.map(k => buildNode(k, childrenMap)),
  };
}

function walkBranch(
  parentKey: string,
  childrenMap: Map<string, MessageItem[]>,
  selections: BranchSelections,
  out: BranchRenderItem[],
): void {
  const kids = childrenMap.get(parentKey);
  if (!kids || kids.length === 0) return;

  // 取选中的 child；若 selections 没有就用第一个
  const selectedId = selections[parentKey] ?? kids[0].id;
  let selected = kids.find(k => String(k.id) === String(selectedId));
  if (!selected) selected = kids[0];

  out.push({
    message: selected,
    siblingCount: kids.length,
    siblingIndex: kids.indexOf(selected) + 1,
    siblingIds: kids.map(k => k.id),
  });

  walkBranch(String(selected.id), childrenMap, selections, out);
}

export type { BranchSelections };

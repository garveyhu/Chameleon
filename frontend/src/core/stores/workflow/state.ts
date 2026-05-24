/** workflow store —— state slice：图编辑器的 UI 态
 *
 * React Flow 的 nodes/edges 仍由 useNodesState/useEdgesState 管理（idiomatic）；
 * 本 store 只收编辑器周边 UI 态：选中节点 / test-run 结果。
 * 切图时调 reset()。
 */

import type { TestRunResult } from '@/system/graphs/types/graph';

export interface WorkflowState {
  /** 当前选中的 React Flow 节点 id（驱动右侧 inspector） */
  selectedNodeId: string | null;
  /** 最近一次 test-run 结果 */
  runResult: TestRunResult | null;
}

export function createInitialWorkflowState(): WorkflowState {
  return {
    selectedNodeId: null,
    runResult: null,
  };
}

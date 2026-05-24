/** workflow store —— state slice：图编辑器的 UI 态
 *
 * React Flow 的 nodes/edges 仍由 useNodesState/useEdgesState 管理（idiomatic）；
 * 运行态由 useGraphRunner 管（随编辑器实例生灭）；本 store 只收选中节点。
 * 切图时调 reset()。
 */

export interface WorkflowState {
  /** 当前选中的 React Flow 节点 id（驱动右侧 inspector） */
  selectedNodeId: string | null;
}

export function createInitialWorkflowState(): WorkflowState {
  return {
    selectedNodeId: null,
  };
}

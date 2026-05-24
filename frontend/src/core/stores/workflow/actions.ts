/** workflow store —— actions slice */

import type { StateCreator } from 'zustand';

import {
  createInitialWorkflowState,
  type WorkflowState,
} from '@/core/stores/workflow/state';
import type { TestRunResult } from '@/system/graphs/types/graph';

export interface WorkflowActions {
  selectNode: (id: string | null) => void;
  setRunResult: (result: TestRunResult | null) => void;
  /** 切图时清空 UI 态 */
  reset: () => void;
}

export type WorkflowStore = WorkflowState & WorkflowActions;

export const createWorkflowActions: StateCreator<
  WorkflowStore,
  [['zustand/devtools', never]],
  [],
  WorkflowActions
> = set => ({
  selectNode: id => set({ selectedNodeId: id }, false, 'workflow/selectNode'),
  setRunResult: result =>
    set({ runResult: result }, false, 'workflow/setRunResult'),
  reset: () => set(createInitialWorkflowState(), false, 'workflow/reset'),
});

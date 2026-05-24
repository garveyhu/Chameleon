/** workflow store —— actions slice */

import type { StateCreator } from 'zustand';

import {
  createInitialWorkflowState,
  type WorkflowState,
} from '@/core/stores/workflow/state';

export interface WorkflowActions {
  selectNode: (id: string | null) => void;
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
  reset: () => set(createInitialWorkflowState(), false, 'workflow/reset'),
});

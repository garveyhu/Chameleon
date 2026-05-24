/** workflow store —— 组装：state + actions slice，套 devtools（仅 dev） */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

import {
  type WorkflowActions,
  createWorkflowActions,
} from '@/core/stores/workflow/actions';
import { createInitialWorkflowState } from '@/core/stores/workflow/state';
import type { WorkflowState } from '@/core/stores/workflow/state';

export type WorkflowStore = WorkflowState & WorkflowActions;

export const useWorkflowStore = create<WorkflowStore>()(
  devtools(
    (...a) => ({
      ...createInitialWorkflowState(),
      ...createWorkflowActions(...a),
    }),
    { name: 'workflow-store', enabled: import.meta.env.DEV },
  ),
);

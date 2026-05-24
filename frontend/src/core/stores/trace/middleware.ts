/** trace store —— 组装：state + actions slice，套 devtools（仅 dev） */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

import {
  type TraceActions,
  createTraceActions,
} from '@/core/stores/trace/actions';
import { createInitialTraceState } from '@/core/stores/trace/state';
import type { TraceViewState } from '@/core/stores/trace/state';

export type TraceStore = TraceViewState & TraceActions;

export const useTraceStore = create<TraceStore>()(
  devtools(
    (...a) => ({
      ...createInitialTraceState(),
      ...createTraceActions(...a),
    }),
    { name: 'trace-store', enabled: import.meta.env.DEV },
  ),
);

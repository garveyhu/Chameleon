/** trace store —— actions slice */

import type { StateCreator } from 'zustand';

import {
  createInitialTraceState,
  type TraceViewMode,
  type TraceViewState,
} from '@/core/stores/trace/state';

export interface TraceActions {
  select: (id: string | null) => void;
  hover: (id: string | null) => void;
  toggleCollapse: (id: string) => void;
  setGanttZoom: (zoom: number) => void;
  setViewMode: (mode: TraceViewMode) => void;
  /** 切 trace 时清空视图态 */
  reset: () => void;
}

export type TraceStore = TraceViewState & TraceActions;

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 8;

export const createTraceActions: StateCreator<
  TraceStore,
  [['zustand/devtools', never]],
  [],
  TraceActions
> = set => ({
  select: id => set({ selectedId: id }, false, 'trace/select'),
  hover: id => set({ hoveredId: id }, false, 'trace/hover'),
  toggleCollapse: id =>
    set(
      s => ({ collapsed: { ...s.collapsed, [id]: !s.collapsed[id] } }),
      false,
      'trace/toggleCollapse',
    ),
  setGanttZoom: zoom =>
    set(
      { ganttZoom: Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoom)) },
      false,
      'trace/setGanttZoom',
    ),
  setViewMode: mode => set({ viewMode: mode }, false, 'trace/setViewMode'),
  reset: () => set(createInitialTraceState(), false, 'trace/reset'),
});

/** trace store —— selectors slice */

import type { TraceViewState } from '@/core/stores/trace/state';

export const isCollapsed = (s: TraceViewState, id: string): boolean =>
  !!s.collapsed[id];

/** kb store —— actions slice */

import type { StateCreator } from 'zustand';

import {
  createInitialKbState,
  type KbHitTestState,
} from '@/core/stores/kb/state';
import type { EntityId } from '@/core/types/api';
import type { RecallMode, SearchHitItem } from '@/system/kbs/types/kb';

export interface KbActions {
  setQuery: (query: string) => void;
  setTopK: (topK: number) => void;
  setMode: (mode: RecallMode) => void;
  setTags: (tags: string) => void;
  setMultiQuery: (on: boolean) => void;
  setHits: (hits: SearchHitItem[]) => void;
  selectChunk: (chunkId: EntityId | null) => void;
  /** 切 KB 时重置，可带该 KB 的默认 top_k / recall_mode */
  reset: (defaults?: { topK?: number; mode?: RecallMode }) => void;
}

export type KbStore = KbHitTestState & KbActions;

export const createKbActions: StateCreator<
  KbStore,
  [['zustand/devtools', never]],
  [],
  KbActions
> = set => ({
  setQuery: query => set({ query }, false, 'kb/setQuery'),
  setTopK: topK => set({ topK }, false, 'kb/setTopK'),
  setMode: mode => set({ mode }, false, 'kb/setMode'),
  setTags: tags => set({ tags }, false, 'kb/setTags'),
  setMultiQuery: multiQuery => set({ multiQuery }, false, 'kb/setMultiQuery'),
  setHits: hits =>
    set({ hits, selectedChunkId: hits[0]?.chunk_id ?? null }, false, 'kb/setHits'),
  selectChunk: selectedChunkId =>
    set({ selectedChunkId }, false, 'kb/selectChunk'),
  reset: defaults =>
    set(
      () => ({
        ...createInitialKbState(),
        ...(defaults?.topK != null ? { topK: defaults.topK } : {}),
        ...(defaults?.mode != null ? { mode: defaults.mode } : {}),
      }),
      false,
      'kb/reset',
    ),
});

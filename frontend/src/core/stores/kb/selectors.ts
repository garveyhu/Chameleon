/** kb store —— selectors slice */

import type { KbHitTestState } from '@/core/stores/kb/state';
import type { SearchHitItem } from '@/system/kbs/types/kb';

export const selectedHit = (
  s: KbHitTestState,
): SearchHitItem | undefined =>
  s.hits.find(h => h.chunk_id === s.selectedChunkId);

/** kb store —— 组装：state + actions slice，套 devtools（仅 dev） */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

import { type KbActions, createKbActions } from '@/core/stores/kb/actions';
import { createInitialKbState } from '@/core/stores/kb/state';
import type { KbHitTestState } from '@/core/stores/kb/state';

export type KbStore = KbHitTestState & KbActions;

export const useKbStore = create<KbStore>()(
  devtools(
    (...a) => ({
      ...createInitialKbState(),
      ...createKbActions(...a),
    }),
    { name: 'kb-store', enabled: import.meta.env.DEV },
  ),
);

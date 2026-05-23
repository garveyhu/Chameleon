/** Workspace 切换全局 store —— P19.3 PR #38
 *
 * 持久化到 localStorage；axios interceptor 取这个值注入 X-Workspace-Id。
 * 切换后由调用方 queryClient.clear() 触发全量 refetch（在 switcher 组件里做）。
 */

import { create } from 'zustand';

const STORAGE_KEY = 'chameleon:workspace_id';

function readPersisted(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writePersisted(value: string | null) {
  try {
    if (value === null) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, value);
  } catch {
    /* SSR / privacy mode → ignore */
  }
}

interface WorkspaceState {
  /** null = admin 看全量 ("all" 模式)；具体 string = 单 ws 视角 */
  currentId: string | null;
  setCurrent: (id: string | null) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  currentId: readPersisted(),
  setCurrent: (id) => {
    writePersisted(id);
    set({ currentId: id });
  },
}));

/** 给 axios interceptor 直接读，避免 React hook 调用 */
export function getCurrentWorkspaceId(): string | null {
  return useWorkspaceStore.getState().currentId;
}

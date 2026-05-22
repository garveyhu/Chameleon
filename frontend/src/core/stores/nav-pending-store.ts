/** 全局导航 pending 状态
 *
 * useSmartNavigate 在等预取时把 pending 置 true，顶部 NavProgressBar
 * 跟着出。多次点击叠加（计数器），最后一个完成才清零。
 */

import { create } from 'zustand';

interface NavPendingState {
  count: number;
  begin: () => void;
  end: () => void;
}

export const useNavPendingStore = create<NavPendingState>(set => ({
  count: 0,
  begin: () => set(s => ({ count: s.count + 1 })),
  end: () => set(s => ({ count: Math.max(0, s.count - 1) })),
}));

export const useIsNavPending = () =>
  useNavPendingStore(s => s.count > 0);

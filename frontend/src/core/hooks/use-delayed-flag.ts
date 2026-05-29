/** 延迟翻转的布尔（双阈值去抖，专治"刚亮就灭"的一闪）：
 * - delay 内 active 又变回 false → 全程不显形（快请求不闪 loading）
 * - minVisibleMs > 0 时，一旦显形至少保持这么久再隐藏（慢请求显形后不会瞬灭）
 *
 * 用法：
 *   const showLoading = useDelayedFlag(loading, 200);        // 仅延迟显形
 *   const showBar = useDelayedFlag(refreshing, 250, 400);    // 延迟 + 最短可见，消除翻页一闪
 */

import { useEffect, useRef, useState } from 'react';

export function useDelayedFlag(active: boolean, delay = 200, minVisibleMs = 0): boolean {
  const [visible, setVisible] = useState(false);
  const shownAtRef = useRef(0);
  useEffect(() => {
    if (active) {
      if (visible) return;
      const t = window.setTimeout(() => {
        shownAtRef.current = Date.now();
        setVisible(true);
      }, delay);
      return () => window.clearTimeout(t);
    }
    if (!visible) return;
    const remain = Math.max(0, minVisibleMs - (Date.now() - shownAtRef.current));
    const t = window.setTimeout(() => setVisible(false), remain);
    return () => window.clearTimeout(t);
  }, [active, visible, delay, minVisibleMs]);
  return visible;
}

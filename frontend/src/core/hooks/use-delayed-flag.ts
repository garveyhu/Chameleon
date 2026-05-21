/** 延迟翻转布尔：active 必须持续 ≥ delay ms 才返回 true，否则全程 false
 *
 * 用途：避免 loading 在 200ms 内回数据时闪烁 skeleton
 */

import { useEffect, useState } from 'react';

export function useDelayedFlag(active: boolean, delay = 200): boolean {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (!active) {
      setShown(false);
      return;
    }
    const t = window.setTimeout(() => setShown(true), delay);
    return () => window.clearTimeout(t);
  }, [active, delay]);
  return shown;
}

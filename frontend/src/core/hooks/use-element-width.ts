/** 用 ResizeObserver 跟踪元素的 contentBox 宽度（px）。
 *
 * 用于需要按容器宽度算几何的场景（如 Gantt 时间轴）。
 */

import { useEffect, useState } from 'react';

export function useElementWidth<T extends HTMLElement>(
  ref: React.RefObject<T | null>,
): number {
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(el.clientWidth);
    const ro = new ResizeObserver(entries => {
      const w = entries[0]?.contentRect.width;
      if (typeof w === 'number') setWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);

  return width;
}

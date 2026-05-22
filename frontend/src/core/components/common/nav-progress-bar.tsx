/** 顶部细横条 —— 智能导航等预取时的进度反馈
 *
 * pending 期间：宽度从 0 % 用 cubic-bezier 慢升到 ~85%（永远到不了 100%）；
 * pending 清零：瞬间冲到 100% + 淡出。
 */

import { useEffect, useState } from 'react';

import { useIsNavPending } from '@/core/stores/nav-pending-store';

export const NavProgressBar = () => {
  const pending = useIsNavPending();
  const [width, setWidth] = useState(0);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    let raf: number;
    let fadeOut: number;
    if (pending) {
      setVisible(true);
      setWidth(0);
      // 下一帧开始爬升，触发 transition
      raf = requestAnimationFrame(() => setWidth(85));
    } else if (visible) {
      // 冲 100 → 淡出
      setWidth(100);
      fadeOut = window.setTimeout(() => {
        setVisible(false);
        setWidth(0);
      }, 250);
    }
    return () => {
      if (raf) cancelAnimationFrame(raf);
      if (fadeOut) clearTimeout(fadeOut);
    };
  }, [pending, visible]);

  if (!visible) return null;
  return (
    <div className="pointer-events-none fixed left-0 right-0 top-0 z-[1000] h-[2px] bg-transparent">
      <div
        className="h-full bg-amber-500 shadow-[0_0_8px_rgba(217,119,6,0.6)] transition-[width,opacity]"
        style={{
          width: `${width}%`,
          opacity: width === 100 && !pending ? 0 : 1,
          transitionDuration: pending ? '600ms' : '200ms',
          transitionTimingFunction: pending
            ? 'cubic-bezier(0.16, 1, 0.3, 1)'
            : 'ease-out',
        }}
      />
    </div>
  );
};

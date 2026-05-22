/** Modal 防误关 hook —— Dirty 时拦截 ESC / 遮罩点击 */

import { useCallback, useRef, useState } from 'react';

interface UseModalDirtyResult {
  dirty: boolean;
  setDirty: (v: boolean) => void;
  /** 包给 Modal 的 onOpenChange；关闭时若 dirty 弹原生 confirm */
  guardedOpenChange: (open: boolean, originalOnChange: (open: boolean) => void) => void;
  /** 重置 dirty 状态（关闭后调用） */
  reset: () => void;
}

export const useModalDirty = (
  confirmMessage = '当前修改尚未保存，确认关闭？',
): UseModalDirtyResult => {
  const [dirty, setDirtyState] = useState(false);
  const dirtyRef = useRef(false);

  const setDirty = useCallback((v: boolean) => {
    dirtyRef.current = v;
    setDirtyState(v);
  }, []);

  const reset = useCallback(() => {
    dirtyRef.current = false;
    setDirtyState(false);
  }, []);

  const guardedOpenChange = useCallback(
    (open: boolean, originalOnChange: (open: boolean) => void) => {
      if (!open && dirtyRef.current) {
        if (typeof window !== 'undefined' && window.confirm(confirmMessage)) {
          reset();
          originalOnChange(false);
        }
        return;
      }
      originalOnChange(open);
    },
    [confirmMessage, reset],
  );

  return { dirty, setDirty, guardedOpenChange, reset };
};

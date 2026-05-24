/** 浏览器内置朗读（Web Speech API）—— 无需后端，play/stop 自切换 */

import { useCallback, useEffect, useState } from 'react';

interface UseSpeechResult {
  /** 当前浏览器是否支持 speechSynthesis */
  supported: boolean;
  speaking: boolean;
  /** 朗读 text；若正在朗读则先停 */
  speak: (text: string) => void;
  stop: () => void;
  /** 正在朗读则停，否则朗读 —— 适合按钮 toggle */
  toggle: (text: string) => void;
}

export function useSpeech(): UseSpeechResult {
  const supported =
    typeof window !== 'undefined' && 'speechSynthesis' in window;
  const [speaking, setSpeaking] = useState(false);

  const stop = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    setSpeaking(false);
  }, [supported]);

  const speak = useCallback(
    (text: string) => {
      if (!supported || !text.trim()) return;
      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(text);
      utter.onend = () => setSpeaking(false);
      utter.onerror = () => setSpeaking(false);
      setSpeaking(true);
      window.speechSynthesis.speak(utter);
    },
    [supported],
  );

  const toggle = useCallback(
    (text: string) => {
      if (speaking) stop();
      else speak(text);
    },
    [speaking, speak, stop],
  );

  // 组件卸载时停止，避免朗读悬挂
  useEffect(() => () => stop(), [stop]);

  return { supported, speaking, speak, stop, toggle };
}

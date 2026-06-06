/** ImageGenLoading —— 文生图等待态：骨架流光 + 旋转 + 计时
 *
 * 替代「一行行打印 SSE 文字」的廉价进度。本地 ComfyUI 出图耗时 ~1 分钟，
 * 用图片占位骨架 + 已用时长，给出「正在出图」的高级观感。测试弹窗与会话气泡共用。
 */

import { ImageIcon, Loader2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { cn } from '@/core/lib/cn';

interface Props {
  /** 占位提示（如「首次含模型加载可能数分钟」） */
  hint?: string;
  /** 额外类名（覆盖宽高比 / 圆角等） */
  className?: string;
}

export const ImageGenLoading = ({ hint, className }: Props) => {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number | null>(null);

  useEffect(() => {
    startRef.current = Date.now();
    const id = setInterval(() => {
      if (startRef.current != null) {
        setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
      }
    }, 250);
    return () => clearInterval(id);
  }, []);

  const label = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`;

  return (
    <div
      className={cn(
        'skeleton relative flex aspect-[4/3] w-full flex-col items-center justify-center gap-2.5 rounded-xl border border-stone-200',
        className,
      )}
    >
      <div className="relative">
        <ImageIcon className="h-9 w-9 text-stone-300" />
        <span className="absolute -right-2 -bottom-2 flex h-5 w-5 items-center justify-center rounded-full bg-white shadow-sm">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-violet-500" />
        </span>
      </div>
      <div className="text-[13px] font-medium text-stone-600">正在生成图片</div>
      <div className="font-mono text-[12px] tabular-nums text-stone-400">{label}</div>
      {hint ? (
        <div className="max-w-[80%] text-center text-[11px] leading-snug text-stone-400">
          {hint}
        </div>
      ) : null}
    </div>
  );
};

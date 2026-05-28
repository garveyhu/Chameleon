/** 画布缩放控件 —— 与 MiniMap 同风格的圆角白卡：− NN% + ⛶（适应画布） */
import { useReactFlow, useViewport } from '@xyflow/react';

import { Maximize2, Minus, Plus } from 'lucide-react';

export const ZoomControl = () => {
  const { zoomIn, zoomOut, fitView } = useReactFlow();
  const { zoom } = useViewport();
  const pct = Math.round(zoom * 100);

  return (
    <div className="flex items-center gap-0.5 rounded-lg border border-stone-200/80 bg-white/95 px-1 py-1 shadow-md backdrop-blur">
      <button
        type="button"
        onClick={() => zoomOut()}
        title="缩小"
        className="flex h-6 w-6 items-center justify-center rounded text-stone-500 transition hover:bg-stone-100 hover:text-stone-800"
      >
        <Minus className="h-3.5 w-3.5" />
      </button>
      <span className="min-w-[40px] text-center font-mono text-[11px] tabular-nums text-stone-600">
        {pct}%
      </span>
      <button
        type="button"
        onClick={() => zoomIn()}
        title="放大"
        className="flex h-6 w-6 items-center justify-center rounded text-stone-500 transition hover:bg-stone-100 hover:text-stone-800"
      >
        <Plus className="h-3.5 w-3.5" />
      </button>
      <div className="mx-0.5 h-3.5 w-px bg-stone-200/80" />
      <button
        type="button"
        onClick={() => fitView({ duration: 200 })}
        title="适应画布"
        className="flex h-6 w-6 items-center justify-center rounded text-stone-500 transition hover:bg-stone-100 hover:text-stone-800"
      >
        <Maximize2 className="h-3.5 w-3.5" />
      </button>
    </div>
  );
};

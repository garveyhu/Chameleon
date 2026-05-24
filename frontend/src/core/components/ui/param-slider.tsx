/** 参数滑块 —— LLM 运行参数（temperature / top_p / max_tokens 等）的统一高级控件。
 *
 * 带标签、当前值徽章、min/max 轨道刻度与可选说明；取代各处散落的裸 range input。
 */

import { cn } from '@/core/lib/cn';

interface ParamSliderProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  /** value === 0 时显示为 ∞（如 max_tokens=0 表示不限） */
  infinityAtZero?: boolean;
  hint?: string;
  className?: string;
}

export const ParamSlider = ({
  label,
  value,
  min,
  max,
  step,
  onChange,
  infinityAtZero = false,
  hint,
  className,
}: ParamSliderProps) => {
  const display = infinityAtZero && value === 0 ? '∞' : value;
  return (
    <div className={cn('space-y-1.5', className)}>
      <div className="flex items-center justify-between">
        <label className="text-[12px] font-medium text-stone-700">{label}</label>
        <span className="rounded bg-stone-100 px-1.5 py-0.5 font-mono text-[11.5px] tabular-nums text-stone-700">
          {display}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full cursor-pointer accent-amber-600"
      />
      <div className="flex justify-between text-[10px] tabular-nums text-stone-400">
        <span>{infinityAtZero && min === 0 ? '0' : min}</span>
        <span>{infinityAtZero ? '∞' : max}</span>
      </div>
      {hint && <p className="text-[10.5px] leading-snug text-stone-500">{hint}</p>}
    </div>
  );
};

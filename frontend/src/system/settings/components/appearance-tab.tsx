/** Settings/外观 tab —— 选 primary / neutral / animation
 *
 * 切换实时生效（preferences store 把 data-attr 挂到 <html>），
 * 同时持久到 localStorage（chameleon:preferences）。
 */

import { Check, Palette, Wand2 } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { cn } from '@/core/lib/cn';
import {
  ANIMATION_MODES,
  NEUTRAL_COLORS,
  PRIMARY_COLORS,
  usePreferencesStore,
} from '@/core/stores/preferences';

export const AppearanceTab = () => {
  const primary = usePreferencesStore(s => s.primaryColor);
  const neutral = usePreferencesStore(s => s.neutralColor);
  const animation = usePreferencesStore(s => s.animationMode);
  const setPref = usePreferencesStore(s => s.set);
  const reset = usePreferencesStore(s => s.reset);

  return (
    <div className="max-w-[760px] space-y-7">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-[14px] font-medium text-stone-900">外观</h2>
          <p className="mt-0.5 text-[11.5px] text-stone-500">
            主题色 / 中性色 / 动画模式 —— 仅本浏览器生效，不上云同步
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={reset}>
          恢复默认
        </Button>
      </header>

      {/* Primary */}
      <section>
        <div className="mb-2 flex items-center gap-1.5 text-[12.5px] font-medium text-stone-800">
          <Palette className="h-3.5 w-3.5 text-stone-500" />
          主题色（primary）
        </div>
        <div className="grid grid-cols-4 gap-2">
          {PRIMARY_COLORS.map(c => (
            <button
              key={c.key}
              type="button"
              onClick={() => setPref('primaryColor', c.key)}
              className={cn(
                'group flex items-center gap-2 rounded-md border px-3 py-2 text-left text-[12px] transition',
                primary === c.key
                  ? 'border-stone-800 bg-stone-50/80'
                  : 'border-stone-200 bg-white hover:border-stone-300',
              )}
            >
              <span
                className="h-5 w-5 shrink-0 rounded-full border border-black/10"
                style={{ background: c.swatch }}
              />
              <span className="min-w-0 flex-1 truncate text-stone-700">
                {c.label}
              </span>
              {primary === c.key && (
                <Check className="h-3 w-3 shrink-0 text-stone-700" />
              )}
            </button>
          ))}
        </div>
      </section>

      {/* Neutral */}
      <section>
        <div className="mb-2 flex items-center gap-1.5 text-[12.5px] font-medium text-stone-800">
          <Palette className="h-3.5 w-3.5 text-stone-500" />
          中性色（neutral）
        </div>
        <div className="grid grid-cols-4 gap-2">
          {NEUTRAL_COLORS.map(c => (
            <button
              key={c.key}
              type="button"
              onClick={() => setPref('neutralColor', c.key)}
              className={cn(
                'group flex items-center gap-2 rounded-md border px-3 py-2 text-left text-[12px] transition',
                neutral === c.key
                  ? 'border-stone-800 bg-stone-50/80'
                  : 'border-stone-200 bg-white hover:border-stone-300',
              )}
            >
              <span
                className="h-5 w-5 shrink-0 rounded border border-black/10"
                style={{ background: c.swatch }}
              />
              <span className="min-w-0 flex-1 truncate text-stone-700">
                {c.label}
              </span>
              {neutral === c.key && (
                <Check className="h-3 w-3 shrink-0 text-stone-700" />
              )}
            </button>
          ))}
        </div>
        <p className="mt-1.5 text-[10.5px] text-stone-500">
          中性色控制全站背景 / 文字基底；改完整页刷新观感最直观
        </p>
      </section>

      {/* Animation */}
      <section>
        <div className="mb-2 flex items-center gap-1.5 text-[12.5px] font-medium text-stone-800">
          <Wand2 className="h-3.5 w-3.5 text-stone-500" />
          动画
        </div>
        <div className="grid grid-cols-3 gap-2">
          {ANIMATION_MODES.map(m => (
            <button
              key={m.key}
              type="button"
              onClick={() => setPref('animationMode', m.key)}
              className={cn(
                'rounded-md border px-3 py-2 text-left text-[12px] transition',
                animation === m.key
                  ? 'border-stone-800 bg-stone-50/80'
                  : 'border-stone-200 bg-white hover:border-stone-300',
              )}
            >
              <div className="flex items-center gap-1.5">
                <span className="font-medium text-stone-800">{m.label}</span>
                {animation === m.key && (
                  <Check className="h-3 w-3 text-stone-700" />
                )}
              </div>
              <div className="mt-1 text-[10.5px] leading-snug text-stone-500">
                {m.desc}
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* Preview */}
      <section className="rounded-md border border-stone-200 bg-warm-2/40 p-4">
        <div className="mb-2 text-[11.5px] font-medium text-stone-700">
          预览
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm">主按钮</Button>
          <Button size="sm" variant="ghost">
            次按钮
          </Button>
          <span className="rounded-full border border-primary-300 bg-primary-50 px-2 py-0.5 text-[10.5px] text-primary-700">
            primary badge
          </span>
          <span className="rounded-full border border-stone-300 bg-white px-2 py-0.5 text-[10.5px] text-stone-700">
            neutral badge
          </span>
          <button
            type="button"
            className="rounded border border-stone-300 bg-white px-2 py-0.5 text-[11px] text-stone-700 transition hover:bg-stone-100"
          >
            hover 测试
          </button>
        </div>
      </section>
    </div>
  );
};

/** 嵌入式智能体外观实时预览
 *
 * 把 ui_config + behavior 渲染成静态预览：右侧浮窗气泡 + 展开后的对话面板。
 * 不发起真实对话，仅展示 UI 效果。
 */

import {
  Bot,
  Copy,
  HelpCircle,
  MessageCircle,
  MessageSquare,
  Minus,
  Paperclip,
  RotateCw,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trash2,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useState } from 'react';

import { cn } from '@/core/lib/cn';
import type {
  Behavior,
  BubbleIcon,
  FontSize,
  ShadowLevel,
  UiConfig,
} from '@/system/embed_configs/types/embed';

const BUBBLE_ICON_MAP: Record<BubbleIcon, LucideIcon> = {
  chat: MessageSquare,
  sparkles: Sparkles,
  'help-circle': HelpCircle,
  'message-circle': MessageCircle,
  bot: Bot,
};

const FONT_SIZE_MAP: Record<FontSize, { panel: string; bubble: string; meta: string }> = {
  sm: { panel: 'text-[12px]', bubble: 'text-[11.5px]', meta: 'text-[10.5px]' },
  md: { panel: 'text-[13px]', bubble: 'text-[12.5px]', meta: 'text-[11.5px]' },
  lg: { panel: 'text-[14.5px]', bubble: 'text-[13.5px]', meta: 'text-[12.5px]' },
};

const SHADOW_MAP: Record<ShadowLevel, string> = {
  none: 'shadow-none',
  sm: 'shadow-sm',
  md: 'shadow-md',
  lg: 'shadow-lg',
};

/** YIQ 亮度判断：浅底（如白）的 header / 元素文字应该用深色，否则白字 */
const isLightHex = (hex: string): boolean => {
  const m = (hex || '').replace('#', '');
  if (m.length !== 3 && m.length !== 6) return false;
  const full = m.length === 3 ? m.split('').map(c => c + c).join('') : m;
  const r = parseInt(full.slice(0, 2), 16);
  const g = parseInt(full.slice(2, 4), 16);
  const b = parseInt(full.slice(4, 6), 16);
  return (r * 299 + g * 587 + b * 114) / 1000 > 175;
};

interface EmbedPreviewProps {
  ui: UiConfig;
  behavior: Behavior;
  className?: string;
}

export const EmbedPreview: React.FC<EmbedPreviewProps> = ({ ui, behavior, className }) => {
  // 默认面板态（主场景）；点击面板右上角的 − 按钮可收起到气泡态预览 bubble + tooltip 效果
  const [bubbleOpen, setBubbleOpen] = useState(true);
  const BubbleIconCmp = BUBBLE_ICON_MAP[ui.bubble_icon] ?? MessageSquare;
  const fontSize = FONT_SIZE_MAP[ui.font_size];

  const isDark = ui.mode === 'dark';
  const paneBg = isDark ? '#1F2937' : '#FFFFFF';
  const paneText = isDark ? '#F9FAFB' : '#111827';
  const subtleText = isDark ? '#9CA3AF' : '#6B7280';
  const dividerBorder = isDark ? '#374151' : '#E5E7EB';
  const inputBg = isDark ? '#111827' : '#F9FAFB';

  const corner = ui.border_radius;

  const positionAnchor =
    ui.bubble_position === 'right-bottom' || ui.bubble_position === 'right-top'
      ? 'right-6'
      : 'left-6';
  const positionVAnchor =
    ui.bubble_position === 'right-bottom' || ui.bubble_position === 'left-bottom'
      ? 'bottom-6'
      : 'top-6';

  // panel 容器要在 preview 框内不溢出，缩放到 ~75%
  const scale = 0.75;
  const scaledW = ui.panel_width * scale;
  const scaledH = ui.panel_height * scale;

  return (
    <div className={cn('relative h-full w-full overflow-hidden', className)}>
      {/* 模拟业务方页面背景 */}
      <div className="absolute inset-0 bg-gradient-to-br from-stone-100 to-stone-50">
        <MockSitePattern />
      </div>

      {/* 浮窗气泡 + 招呼语 tooltip */}
      <div
        className={cn(
          'absolute z-10 transition-opacity',
          positionAnchor,
          positionVAnchor,
          bubbleOpen && !ui.bubble_persist_when_open && 'opacity-0',
        )}
      >
        <BubbleWithTooltip
          ui={ui}
          BubbleIconCmp={BubbleIconCmp}
          shadowClass={SHADOW_MAP[ui.shadow]}
          hidden={bubbleOpen && ui.bubble_tooltip_dismiss_on_open}
          onToggle={() => setBubbleOpen(o => !o)}
        />
      </div>

      {/* 对话面板（缩放显示） */}
      {bubbleOpen ? (
        <div
          className={cn(
            'absolute',
            positionAnchor === 'right-6' ? 'right-6' : 'left-6',
            positionVAnchor === 'bottom-6' ? 'bottom-20' : 'top-20',
            'z-10 origin-bottom-right',
          )}
        >
          <div
            className={cn(
              'flex flex-col overflow-hidden border',
              SHADOW_MAP[ui.shadow],
              fontSize.panel,
            )}
            style={{
              width: scaledW,
              height: scaledH,
              borderRadius: corner,
              borderColor: dividerBorder,
              backgroundColor: paneBg,
              color: paneText,
            }}
          >
            {/* header —— 文字色按 header_bg 亮度自适应（白底 → 深字） */}
            {(() => {
              const headerLight = isLightHex(ui.header_bg);
              const headerText = headerLight ? paneText : '#FFFFFF';
              const closeHover = headerLight ? 'hover:bg-stone-100' : 'hover:bg-white/10';
              const headerBorderBottom = headerLight
                ? `1px solid ${dividerBorder}`
                : 'none';
              return (
                <div
                  className="flex items-center justify-between px-3 py-2.5"
                  style={{
                    backgroundColor: ui.header_bg,
                    color: headerText,
                    borderTopLeftRadius: corner,
                    borderTopRightRadius: corner,
                    borderBottom: headerBorderBottom,
                  }}
                >
                  <div className="flex items-center gap-2">
                    {ui.icon_url ? (
                      <img
                        src={ui.icon_url}
                        alt=""
                        className="h-[20px] w-[20px] rounded object-cover"
                      />
                    ) : (
                      <span className="text-[18px] leading-none">{ui.icon_emoji}</span>
                    )}
                    <div className="leading-tight">
                      <div className={cn('font-medium', fontSize.bubble)}>{ui.title}</div>
                      <div
                        className={cn(fontSize.meta)}
                        style={{ opacity: headerLight ? 0.6 : 0.8 }}
                      >
                        {ui.subtitle}
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    className={cn('rounded p-0.5 transition', closeHover)}
                    style={{ color: headerText, opacity: 0.8 }}
                    onClick={() => setBubbleOpen(false)}
                    title="收起预览"
                  >
                    <Minus className="h-3.5 w-3.5" />
                  </button>
                </div>
              );
            })()}

            {/* message list */}
            <div className="flex-1 space-y-2 overflow-y-auto px-3 py-2.5">
              {ui.greeting ? (
                <BubbleMsg
                  role="assistant"
                  text={ui.greeting}
                  emoji={ui.icon_emoji}
                  iconUrl={ui.icon_url}
                  themeColor={ui.theme_color}
                  paneText={paneText}
                  subtleText={subtleText}
                  isDark={isDark}
                  cornerPx={corner}
                  fontSize={fontSize}
                  showCitation={behavior.show_citations}
                  showFeedback={behavior.show_feedback}
                />
              ) : null}

              {behavior.suggested_questions.length > 0 ? (
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {behavior.suggested_questions.map((q, i) => (
                    <button
                      type="button"
                      key={i}
                      className={cn(
                        'rounded-full border px-2.5 py-1 transition',
                        fontSize.meta,
                      )}
                      style={{
                        borderColor: ui.theme_color,
                        color: ui.theme_color,
                        backgroundColor: 'transparent',
                      }}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>

            {/* input bar —— 跟 widget 对齐：去顶线 / textarea 方形圆角 + shadow / 方形 send */}
            <div
              className="flex items-center gap-1.5 px-3 py-2.5"
              style={{ backgroundColor: paneBg }}
            >
              {behavior.allow_file_upload ? (
                <button
                  type="button"
                  className="flex h-7 w-7 items-center justify-center rounded-md transition"
                  style={{ color: subtleText }}
                >
                  <Paperclip className="h-3.5 w-3.5" />
                </button>
              ) : null}
              <div
                className={cn('flex-1 rounded-lg border px-2.5 py-1.5', fontSize.meta)}
                style={{
                  borderColor: dividerBorder,
                  backgroundColor: inputBg,
                  color: subtleText,
                  boxShadow: '0 1px 2px rgba(15,23,42,.04), 0 4px 12px rgba(15,23,42,.04)',
                }}
              >
                {ui.placeholder || '请输入…'}
              </div>
              <button
                type="button"
                className="flex h-7 w-7 items-center justify-center rounded-md text-white"
                style={{
                  backgroundColor: ui.theme_color,
                  boxShadow: `0 2px 6px ${ui.theme_color}40`,
                }}
              >
                <Send className="h-3 w-3" />
              </button>
            </div>
            {/* powered-by 水印 */}
            {ui.show_powered_by !== false ? (
              <div
                className={cn('text-center py-1', fontSize.meta)}
                style={{ color: subtleText, opacity: 0.7 }}
              >
                {ui.powered_by_text || 'powered by Chameleon'}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* 预览提示角标 */}
      <div className="absolute left-2 top-2 rounded-md border border-stone-200 bg-white/80 px-1.5 py-0.5 text-[10px] text-stone-500 backdrop-blur">
        实时预览（缩放 75%）
      </div>
    </div>
  );
};

// ── 子组件 ────────────────────────────────────────────────────

interface BubbleMsgProps {
  role: 'assistant' | 'user';
  text: string;
  emoji: string;
  iconUrl: string | null;
  themeColor: string;
  paneText: string;
  subtleText: string;
  isDark: boolean;
  cornerPx: number;
  fontSize: { panel: string; bubble: string; meta: string };
  showCitation: boolean;
  showFeedback: boolean;
}

const BubbleMsg: React.FC<BubbleMsgProps> = ({
  role,
  text,
  emoji,
  iconUrl,
  themeColor,
  paneText,
  subtleText,
  isDark,
  cornerPx,
  fontSize,
  showCitation,
  showFeedback,
}) => {
  if (role === 'user') {
    return (
      <div className="flex justify-end">
        <div
          className={cn('max-w-[80%] px-3 py-1.5 text-white', fontSize.panel)}
          style={{ backgroundColor: themeColor, borderRadius: cornerPx }}
        >
          {text}
        </div>
      </div>
    );
  }
  return (
    <div className="flex items-start gap-1.5">
      {iconUrl ? (
        <img src={iconUrl} alt="" className="h-[18px] w-[18px] rounded object-cover" />
      ) : (
        <span className="text-[16px] leading-none">{emoji}</span>
      )}
      <div className="max-w-[80%] space-y-1">
        <div
          className={cn('whitespace-pre-line px-2.5 py-1.5', fontSize.panel)}
          style={{
            backgroundColor: isDark ? '#374151' : '#F3F4F6',
            color: paneText,
            borderRadius: cornerPx,
          }}
        >
          {text}
        </div>
        {showCitation ? (
          <div
            className={cn('flex items-center gap-1', fontSize.meta)}
            style={{ color: subtleText }}
          >
            <span className="rounded border border-stone-300/60 px-1.5 text-[10px]">
              📎 引用 · 来源 KB
            </span>
          </div>
        ) : null}
        {/* actions：copy / regen / [thumbs up / down 受配置] / trash —— 跟 widget 对齐 */}
        <div className="flex items-center gap-1 pt-0.5" style={{ color: subtleText }}>
          <button type="button" className="rounded p-0.5 transition hover:bg-stone-200/50">
            <Copy className="h-3 w-3" />
          </button>
          <button type="button" className="rounded p-0.5 transition hover:bg-stone-200/50">
            <RotateCw className="h-3 w-3" />
          </button>
          {showFeedback ? (
            <>
              <button type="button" className="rounded p-0.5 transition hover:bg-stone-200/50">
                <ThumbsUp className="h-3 w-3" />
              </button>
              <button type="button" className="rounded p-0.5 transition hover:bg-stone-200/50">
                <ThumbsDown className="h-3 w-3" />
              </button>
            </>
          ) : null}
          <button type="button" className="rounded p-0.5 transition hover:bg-stone-200/50">
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      </div>
    </div>
  );
};

/** 浮窗气泡 + 旁边招呼语 tooltip（含 orbit 圆弧文字） */
const BubbleWithTooltip: React.FC<{
  ui: UiConfig;
  BubbleIconCmp: LucideIcon;
  shadowClass: string;
  hidden: boolean;
  onToggle: () => void;
}> = ({ ui, BubbleIconCmp, shadowClass, hidden, onToggle }) => {
  const tip = ui.bubble_tooltip_text || '';
  const tipPos = ui.bubble_tooltip_position || 'left';
  const tipStyle: React.CSSProperties = {
    color: ui.bubble_tooltip_color || '#1f2937',
    fontSize: `${ui.bubble_tooltip_font_size || 13}px`,
    fontWeight: ui.bubble_tooltip_font_weight === 'bold' ? 700 : 400,
  };
  const isOrbit = tipPos === 'orbit';

  // bubble 实际尺寸（受 bubble_size 控制，admin 端 40–96px）
  const bs = Math.max(40, Math.min(96, ui.bubble_size ?? 56));
  const iconPx = Math.round(bs * 0.47);

  const bubbleButton = (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        'relative flex items-center justify-center text-white transition hover:scale-105',
        !ui.bubble_transparent && !ui.bubble_image_url && shadowClass,
      )}
      style={{
        width: bs,
        height: bs,
        backgroundColor:
          ui.bubble_transparent || ui.bubble_image_url ? 'transparent' : ui.bubble_color,
        borderRadius: '50%',
        color: ui.bubble_transparent ? ui.bubble_color : '#fff',
      }}
      title="预览气泡（点击切换面板）"
    >
      {ui.bubble_image_url ? (
        <img
          src={ui.bubble_image_url}
          alt=""
          className="h-full w-full rounded-full object-cover"
        />
      ) : (
        <BubbleIconCmp style={{ width: iconPx, height: iconPx }} strokeWidth={1.75} />
      )}
    </button>
  );

  // 没文字 → 仅 bubble
  if (!tip) {
    return <div className="inline-block">{bubbleButton}</div>;
  }

  // orbit：SVG 绝对定位在 wrap 上方（不放进 button，避免 overflow:hidden 截断）
  // hidden 只对 SVG fade，bubble 保持显示
  if (isOrbit) {
    return (
      <div className="relative inline-block">
        <div className={cn('transition-opacity', hidden && 'opacity-0')}>
          <OrbitTip text={tip} style={tipStyle} bubbleSize={bs} />
        </div>
        {bubbleButton}
      </div>
    );
  }

  // 直线方向：DOM 顺序是 {tooltip}{bubble}，所以 row=tooltip 在左、col=tooltip 在上
  const wrapClass =
    tipPos === 'left'
      ? 'flex flex-row items-center gap-2.5'
      : tipPos === 'right'
        ? 'flex flex-row-reverse items-center gap-2.5'
        : tipPos === 'top'
          ? 'flex flex-col items-center gap-2'
          : 'flex flex-col-reverse items-center gap-2';
  const transparentTip = ui.bubble_tooltip_transparent;
  return (
    <div className={cn(wrapClass)}>
      {/* hidden 只对 tooltip fade，bubble 不动 */}
      <div
        style={tipStyle}
        className={cn(
          'whitespace-nowrap transition-opacity',
          transparentTip
            ? 'px-1 py-0.5'
            : 'rounded-2xl border border-stone-200 bg-white px-3 py-1.5 shadow-md',
          hidden && 'opacity-0',
        )}
      >
        {tip}
      </div>
      {bubbleButton}
    </div>
  );
};

const OrbitTip: React.FC<{
  text: string;
  style: React.CSSProperties;
  bubbleSize: number;
}> = ({ text, style, bubbleSize }) => {
  // path 走"从右到左 + sweepFlag=0"上半圆，让 textPath 文字头朝上
  const r = bubbleSize / 2 + 10;
  const cx = bubbleSize / 2;
  const cy = r + 8;
  const w = cx * 2 + 24;
  const h = r + 28;
  const path = `M ${cx + r} ${cy} A ${r} ${r} 0 0 0 ${cx - r} ${cy}`;
  return (
    <svg
      width={w}
      height={h}
      viewBox={`-12 0 ${w} ${h}`}
      aria-hidden="true"
      className="pointer-events-none absolute left-1/2 -translate-x-1/2"
      style={{ bottom: '100%', marginBottom: -6 }}
    >
      <defs>
        <path id="preview-orbit-path" d={path} fill="none" />
      </defs>
      <text style={style} dy={-6}>
        <textPath href="#preview-orbit-path" startOffset="50%" textAnchor="middle">
          {text}
        </textPath>
      </text>
    </svg>
  );
};

// 装饰用的伪页面斑纹
const MockSitePattern = () => (
  <div className="absolute inset-0 opacity-40">
    <div className="absolute left-6 top-6 h-3 w-32 rounded bg-stone-300" />
    <div className="absolute left-6 top-12 h-2 w-48 rounded bg-stone-200" />
    <div className="absolute left-6 top-20 h-24 w-64 rounded-lg bg-stone-200/80" />
    <div className="absolute left-6 top-48 h-2 w-56 rounded bg-stone-200" />
    <div className="absolute left-6 top-52 h-2 w-40 rounded bg-stone-200" />
    <div className="absolute left-6 top-56 h-2 w-52 rounded bg-stone-200" />
  </div>
);

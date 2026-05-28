/** 嵌入式智能体外观实时预览
 *
 * 把 ui_config + behavior 渲染成静态预览：右侧浮窗气泡 + 展开后的对话面板。
 * 不发起真实对话，仅展示 UI 效果。
 */

import {
  Bot,
  HelpCircle,
  MessageCircle,
  MessageSquare,
  Minus,
  Paperclip,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
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
      <div className={cn('absolute', positionAnchor, positionVAnchor, 'z-10')}>
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
            {/* header */}
            <div
              className="flex items-center justify-between px-3 py-2.5"
              style={{
                backgroundColor: ui.header_bg,
                color: '#fff',
                borderTopLeftRadius: corner,
                borderTopRightRadius: corner,
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
                  <div className={cn(fontSize.meta, 'opacity-80')}>{ui.subtitle}</div>
                </div>
              </div>
              <button
                type="button"
                className="rounded p-0.5 text-white/80 transition hover:bg-white/10"
                onClick={() => setBubbleOpen(false)}
                title="收起预览"
              >
                <Minus className="h-3.5 w-3.5" />
              </button>
            </div>

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

            {/* input bar */}
            <div
              className="flex items-center gap-2 border-t px-3 py-2.5"
              style={{ borderColor: dividerBorder, backgroundColor: inputBg }}
            >
              {behavior.allow_file_upload ? (
                <button
                  type="button"
                  className="rounded p-1 transition"
                  style={{ color: subtleText }}
                >
                  <Paperclip className="h-3.5 w-3.5" />
                </button>
              ) : null}
              <div
                className={cn('flex-1', fontSize.meta)}
                style={{
                  color: subtleText,
                }}
              >
                {ui.placeholder || '请输入…'}
              </div>
              <button
                type="button"
                className="flex h-6 w-6 items-center justify-center rounded text-white"
                style={{ backgroundColor: ui.theme_color }}
              >
                <Send className="h-3 w-3" />
              </button>
            </div>
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
        {showFeedback ? (
          <div className="flex items-center gap-1 pt-0.5">
            <button
              type="button"
              className="rounded p-0.5 transition hover:bg-stone-200/50"
              style={{ color: subtleText }}
            >
              <ThumbsUp className="h-3 w-3" />
            </button>
            <button
              type="button"
              className="rounded p-0.5 transition hover:bg-stone-200/50"
              style={{ color: subtleText }}
            >
              <ThumbsDown className="h-3 w-3" />
            </button>
          </div>
        ) : null}
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

  // orbit：SVG 绝对定位在 wrap 上方（不放进 button，避免 overflow:hidden 截断）
  if (tip && isOrbit) {
    return (
      <div
        className={cn('relative inline-block transition-opacity', hidden && 'opacity-0')}
      >
        <OrbitTip text={tip} style={tipStyle} bubbleSize={bs} />
        {bubbleButton}
      </div>
    );
  }

  if (!tip || hidden) {
    return (
      <div className={cn('inline-block transition-opacity', hidden && 'opacity-0')}>
        {bubbleButton}
      </div>
    );
  }

  // 直线方向：四向 flex 布局
  const wrapClass =
    tipPos === 'left'
      ? 'flex flex-row-reverse items-center gap-2.5'
      : tipPos === 'right'
        ? 'flex flex-row items-center gap-2.5'
        : tipPos === 'top'
          ? 'flex flex-col-reverse items-center gap-2'
          : 'flex flex-col items-center gap-2';
  return (
    <div className={cn(wrapClass)}>
      <div
        style={tipStyle}
        className={cn(
          'whitespace-nowrap rounded-2xl border border-stone-200 bg-white px-3 py-1.5 shadow-md',
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
  const r = bubbleSize / 2 + 10;
  const cx = bubbleSize / 2;
  const cy = bubbleSize / 2;
  const w = cx * 2 + 16;
  const h = r + 16;
  const path = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;
  return (
    <svg
      width={w}
      height={h}
      viewBox={`-8 0 ${w} ${h}`}
      aria-hidden="true"
      className="pointer-events-none absolute left-1/2 -translate-x-1/2"
      style={{ bottom: '100%', marginBottom: -8 }}
    >
      <defs>
        <path id="preview-orbit-path" d={path} />
      </defs>
      <text style={style}>
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

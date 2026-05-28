/** widget 样式表 —— 注入 shadow DOM 防业务方页面样式污染
 *
 * 所有视觉调参都由 admin 端 ui_config 驱动；本文件只是把字段映射到 CSS。
 */

import type { FontSize, ShadowLevel, ThemeMode, UiConfig } from './types';

interface ResolvedTheme {
  themeColor: string;
  bubbleColor: string;
  headerBg: string;
  headerText: string;
  paneBg: string;
  paneText: string;
  subtleText: string;
  borderColor: string;
  inputBg: string;
  inputBorder: string;
  inputFocus: string;
  userBubble: string;
  userBubbleText: string;
  botBubble: string;
  botBubbleBorder: string;
  citationBg: string;
  citationBorder: string;
  citationText: string;
  errorBg: string;
  errorBorder: string;
  errorText: string;
  brandBg: string;
  brandText: string;
}

const FONT_PX: Record<FontSize, { panel: number; meta: number }> = {
  sm: { panel: 12.5, meta: 11 },
  md: { panel: 13.5, meta: 12 },
  lg: { panel: 14.5, meta: 12.5 },
};

const SHADOW_CSS: Record<ShadowLevel, string> = {
  none: 'none',
  sm: '0 2px 8px rgba(0,0,0,.08)',
  md: '0 6px 18px rgba(0,0,0,.12), 0 2px 6px rgba(0,0,0,.06)',
  lg: '0 12px 40px rgba(0,0,0,.18), 0 4px 12px rgba(0,0,0,.08)',
};

const isDark = (mode: ThemeMode): boolean => {
  if (mode === 'dark') return true;
  if (mode === 'auto') {
    return (
      typeof window !== 'undefined' &&
      window.matchMedia &&
      window.matchMedia('(prefers-color-scheme: dark)').matches
    );
  }
  return false;
};

const resolveTheme = (ui: UiConfig): ResolvedTheme => {
  const themeColor = ui.theme_color || '#2563EB';
  const bubbleColor = ui.bubble_color || themeColor;
  const headerBg = ui.header_bg || themeColor;
  const dark = isDark(ui.mode || 'light');
  return {
    themeColor,
    bubbleColor,
    headerBg,
    headerText: '#FFFFFF',
    paneBg: dark ? '#0F172A' : '#FFFFFF',
    paneText: dark ? '#F1F5F9' : '#111827',
    subtleText: dark ? '#94A3B8' : '#6B7280',
    borderColor: dark ? '#1E293B' : '#E5E7EB',
    inputBg: dark ? '#0F172A' : '#FFFFFF',
    inputBorder: dark ? '#334155' : '#D1D5DB',
    inputFocus: themeColor,
    userBubble: themeColor,
    userBubbleText: '#FFFFFF',
    botBubble: dark ? '#1E293B' : '#FFFFFF',
    botBubbleBorder: dark ? '#334155' : '#E5E7EB',
    citationBg: dark ? '#1E293B' : '#F8FAFC',
    citationBorder: dark ? '#334155' : '#E2E8F0',
    citationText: dark ? '#CBD5E1' : '#475569',
    errorBg: dark ? '#7F1D1D' : '#FEF2F2',
    errorBorder: dark ? '#991B1B' : '#FECACA',
    errorText: dark ? '#FCA5A5' : '#B91C1C',
    brandBg: dark ? '#0F172A' : '#FFFFFF',
    brandText: dark ? '#475569' : '#94A3B8',
  };
};

export const buildStyles = (ui: UiConfig): string => {
  const theme = resolveTheme(ui);
  const radius = Math.max(0, Math.min(32, ui.border_radius ?? 12));
  const bubbleRadius = radius >= 16 ? 16 : 12;
  const font = FONT_PX[ui.font_size ?? 'md'];
  const shadow = SHADOW_CSS[ui.shadow ?? 'lg'];
  const panelW = Math.max(280, Math.min(520, ui.panel_width ?? 400));
  const panelH = Math.max(360, Math.min(800, ui.panel_height ?? 600));

  return `
:host {
  all: initial;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}

* { box-sizing: border-box; }

.bubble {
  position: fixed;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: ${theme.bubbleColor};
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: ${shadow};
  z-index: 2147483647;
  border: none;
  transition: transform .15s ease, box-shadow .15s ease;
}
.bubble:hover { transform: scale(1.06); }
.bubble.pos-right-bottom { right: 24px; bottom: 24px; }
.bubble.pos-left-bottom  { left: 24px;  bottom: 24px; }
.bubble.pos-right-top    { right: 24px; top: 24px; }
.bubble.pos-left-top     { left: 24px;  top: 24px; }
.bubble svg { width: 26px; height: 26px; }

.panel {
  position: fixed;
  width: ${panelW}px;
  height: ${panelH}px;
  max-height: calc(100vh - 120px);
  max-width: calc(100vw - 24px);
  background: ${theme.paneBg};
  color: ${theme.paneText};
  border-radius: ${radius}px;
  box-shadow: ${shadow};
  display: flex;
  flex-direction: column;
  overflow: hidden;
  z-index: 2147483647;
  opacity: 0;
  transform: translateY(8px) scale(.98);
  pointer-events: none;
  transition: opacity .18s ease, transform .18s ease;
}
.panel.open {
  opacity: 1;
  transform: translateY(0) scale(1);
  pointer-events: auto;
}
.panel.pos-right-bottom { right: 24px; bottom: 96px; }
.panel.pos-left-bottom  { left: 24px;  bottom: 96px; }
.panel.pos-right-top    { right: 24px; top: 96px; }
.panel.pos-left-top     { left: 24px;  top: 96px; }

/* ─── 历史会话 overlay（FastGPT 风格，覆盖主对话区） ───────────── */
.sidebar {
  position: absolute; inset: 0; z-index: 5;
  display: flex; flex-direction: column;
  background: ${theme.paneBg};
  border-radius: inherit;
  opacity: 0; transform: translateY(-4px);
  pointer-events: none;
  transition: opacity .14s ease, transform .14s ease;
}
.panel.sidebar-open .sidebar {
  opacity: 1; transform: translateY(0); pointer-events: auto;
}

.sidebar-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid ${theme.borderColor};
}
.sidebar-title {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 14px; font-weight: 600; color: ${theme.paneText};
}
.sidebar-title::before {
  content: ''; display: block;
  width: 3px; height: 14px; border-radius: 2px;
  background: ${theme.themeColor};
}
.sidebar-head-actions { display: inline-flex; align-items: center; gap: 6px; }

.new-session-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 12px;
  background: ${theme.paneBg};
  color: ${theme.themeColor};
  border: 1px solid ${theme.themeColor}55;
  border-radius: 999px;
  cursor: pointer;
  font-size: 12px; font-weight: 500;
  transition: background .12s ease, border-color .12s ease;
}
.new-session-btn:hover { background: ${theme.themeColor}0d; border-color: ${theme.themeColor}; }
.new-session-btn svg { width: 14px; height: 14px; }

.sidebar-close {
  display: inline-flex; align-items: center; justify-content: center;
  width: 26px; height: 26px;
  background: transparent; border: none; border-radius: 5px;
  color: ${theme.subtleText};
  cursor: pointer;
}
.sidebar-close:hover { background: rgba(127,127,127,.14); color: ${theme.paneText}; }
.sidebar-close svg { width: 16px; height: 16px; }

.sidebar-list {
  flex: 1; overflow-y: auto; padding: 8px;
  scrollbar-width: thin;
}
.sidebar-list::-webkit-scrollbar { width: 4px; }
.sidebar-list::-webkit-scrollbar-thumb { background: ${theme.borderColor}; border-radius: 2px; }

.sidebar-empty {
  padding: 32px 12px; text-align: center;
  font-size: 12px; color: ${theme.subtleText};
}

.sidebar-item {
  position: relative;
  display: flex; align-items: center; gap: 10px;
  padding: 9px 10px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: ${theme.paneText};
  transition: background .12s ease;
}
.sidebar-item + .sidebar-item { margin-top: 2px; }
.sidebar-item:hover { background: ${theme.paneBg === '#FFFFFF' ? 'rgba(0,0,0,.04)' : 'rgba(255,255,255,.04)'}; }
.sidebar-item.active {
  background: ${theme.themeColor}14;
  color: ${theme.themeColor};
}

.sidebar-item-avatar {
  width: 24px; height: 24px; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: 50%;
  background: ${theme.themeColor}1a;
  color: ${theme.themeColor};
  font-size: 14px; line-height: 1;
  overflow: hidden;
}
.sidebar-item-avatar img { width: 100%; height: 100%; object-fit: cover; }

.sidebar-item-title {
  flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.sidebar-item-edit {
  flex: 1; min-width: 0;
  font: inherit; color: inherit;
  background: transparent; border: 1px solid ${theme.themeColor};
  border-radius: 5px; padding: 2px 6px; outline: none;
}
.sidebar-item-time {
  flex-shrink: 0;
  font-size: 11px;
  color: ${theme.subtleText};
}
.sidebar-item.active .sidebar-item-time { color: ${theme.themeColor}; opacity: .7; }

.sidebar-item-menu { flex-shrink: 0; opacity: 0; transition: opacity .12s; }
.sidebar-item:hover .sidebar-item-menu, .sidebar-item.active .sidebar-item-menu { opacity: 1; }
.sidebar-item-more {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; padding: 0;
  background: transparent; border: none; border-radius: 4px;
  color: ${theme.subtleText};
  cursor: pointer;
}
.sidebar-item-more:hover { background: rgba(127,127,127,.16); color: ${theme.paneText}; }
.sidebar-item-more svg { width: 14px; height: 14px; }

.sidebar-item-pop {
  position: absolute; top: calc(100% + 2px); right: 6px; z-index: 12;
  background: ${theme.paneBg};
  border: 1px solid ${theme.borderColor};
  border-radius: 8px;
  box-shadow: 0 12px 24px rgba(0,0,0,.14);
  padding: 4px;
  min-width: 100px;
}
.sidebar-item-pop button {
  display: flex; align-items: center; gap: 6px;
  width: 100%; padding: 6px 8px;
  background: transparent; border: none; border-radius: 5px;
  color: ${theme.paneText};
  cursor: pointer;
  font-size: 12px; text-align: left;
}
.sidebar-item-pop button svg { width: 12px; height: 12px; opacity: .65; }
.sidebar-item-pop button:hover { background: rgba(127,127,127,.12); }
.sidebar-item-pop button.danger { color: #dc2626; }
.sidebar-item-pop button.danger:hover { background: rgba(220,38,38,.08); }

.sidebar-item-confirm {
  position: absolute; inset: 0;
  display: flex; align-items: center; gap: 4px;
  padding: 0 10px;
  background: ${theme.paneBg};
  border-radius: 8px;
  font-size: 12px; color: ${theme.paneText};
}
.sidebar-item-confirm span { flex: 1; }
.sidebar-item-confirm button {
  background: transparent; border: none; border-radius: 4px;
  padding: 3px 8px;
  font-size: 12px; cursor: pointer;
  color: ${theme.subtleText};
}
.sidebar-item-confirm button:hover { background: rgba(127,127,127,.14); color: ${theme.paneText}; }
.sidebar-item-confirm button.danger { color: #dc2626; }
.sidebar-item-confirm button.danger:hover { background: rgba(220,38,38,.1); color: #dc2626; }

.sidebar-toggle {
  display: inline-flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; padding: 0;
  background: transparent; border: none; border-radius: 5px;
  color: ${theme.headerText};
  cursor: pointer; flex-shrink: 0;
  margin-right: 2px;
}
.sidebar-toggle:hover { background: rgba(255,255,255,.18); }
.sidebar-toggle svg { width: 16px; height: 16px; }

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: ${theme.headerBg};
  color: ${theme.headerText};
}
.header-main {
  display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0;
}
.header-emoji { font-size: 22px; line-height: 1; }
.header-emoji img {
  width: 22px; height: 22px; border-radius: 4px; object-fit: cover; display: block;
}
.header-text { flex: 1; min-width: 0; }
.header-title { font-size: 14px; font-weight: 600; line-height: 1.3; }
.header-sub { font-size: 12px; opacity: .85; margin-top: 2px; }
.close-btn {
  background: transparent;
  border: none;
  color: ${theme.headerText};
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  display: flex;
  align-items: center;
}
.close-btn:hover { background: rgba(255,255,255,.18); }
.close-btn svg { width: 18px; height: 18px; }

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: ${theme.paneBg};
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.msg { display: flex; max-width: 88%; gap: 6px; }
.msg.user { align-self: flex-end; flex-direction: row-reverse; }
.msg.bot { align-self: flex-start; }
.msg.bot .avatar {
  font-size: 18px; line-height: 1; padding-top: 3px; flex-shrink: 0;
}
.msg.bot .avatar img {
  width: 22px; height: 22px; border-radius: 4px; object-fit: cover; display: block;
}

.bubble-text {
  padding: 9px 12px;
  border-radius: ${bubbleRadius}px;
  font-size: ${font.panel}px;
  line-height: 1.6;
  word-wrap: break-word;
  overflow-wrap: anywhere;
}
.bubble-text > :first-child { margin-top: 0; }
.bubble-text > :last-child { margin-bottom: 0; }
.bubble-text p { margin: 0 0 8px; }
.bubble-text p:last-child { margin-bottom: 0; }
.bubble-text strong { font-weight: 600; }
.bubble-text em { font-style: italic; }
.bubble-text code {
  background: rgba(127,127,127,.18);
  padding: 1px 5px;
  border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.92em;
}
.bubble-text pre {
  background: rgba(15,23,42,.08);
  padding: 8px 10px;
  border-radius: 8px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.92em;
  overflow-x: auto;
  margin: 6px 0;
}
.bubble-text pre code {
  background: transparent;
  padding: 0;
}
.bubble-text ul, .bubble-text ol {
  margin: 4px 0 6px;
  padding-left: 20px;
}
.bubble-text li { margin: 1px 0; }
.bubble-text a {
  color: ${theme.themeColor};
  text-decoration: underline;
}
.bubble-text h1, .bubble-text h2, .bubble-text h3 {
  font-weight: 600;
  margin: 8px 0 4px;
  line-height: 1.3;
}
.bubble-text h1 { font-size: 1.15em; }
.bubble-text h2 { font-size: 1.08em; }
.bubble-text h3 { font-size: 1.02em; }
.bubble-text blockquote {
  border-left: 3px solid ${theme.borderColor};
  padding-left: 8px;
  margin: 6px 0;
  color: ${theme.subtleText};
}

.msg.user .bubble-text {
  background: ${theme.userBubble};
  color: ${theme.userBubbleText};
  border-bottom-right-radius: 4px;
}
.msg.bot .bubble-text {
  background: ${theme.botBubble};
  color: ${theme.paneText};
  border: 1px solid ${theme.botBubbleBorder};
  border-bottom-left-radius: 4px;
}
.msg.error .bubble-text {
  background: ${theme.errorBg};
  color: ${theme.errorText};
  border-color: ${theme.errorBorder};
}

.typing {
  display: inline-flex;
  gap: 4px;
  padding: 4px 0;
}
.typing span {
  width: 6px; height: 6px; border-radius: 50%;
  background: ${theme.subtleText};
  animation: typing 1.2s infinite ease-in-out;
}
.typing span:nth-child(2) { animation-delay: .15s; }
.typing span:nth-child(3) { animation-delay: .3s; }
@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); opacity: .4; }
  30% { transform: translateY(-4px); opacity: 1; }
}

.msg-tools {
  display: flex; align-items: center; gap: 4px;
  margin-top: 4px;
  font-size: ${font.meta}px;
  color: ${theme.subtleText};
}
.msg-tools button {
  background: transparent; border: none; cursor: pointer;
  color: ${theme.subtleText}; padding: 2px 4px; border-radius: 4px;
  line-height: 0;
}
.msg-tools button:hover { background: rgba(127,127,127,.15); color: ${theme.paneText}; }
.msg-tools button:disabled { cursor: not-allowed; opacity: .4; }
.msg-tools button:disabled:hover { background: transparent; color: ${theme.subtleText}; }
.msg-tools button.active { color: ${theme.themeColor}; }
.msg-tools button.danger:hover { background: rgba(220,38,38,.10); color: #dc2626; }
.msg-tools svg { width: 13px; height: 13px; }
/* user 消息 Actions：默认隐藏，hover 显（避免每条 user 都长一排按钮） */
.msg.user .msg-tools { opacity: 0; transition: opacity .15s; }
.msg.user:hover .msg-tools { opacity: 1; }

.citations {
  display: flex; flex-wrap: wrap; gap: 4px;
  margin-top: 6px;
}
.citation-chip {
  display: inline-flex; align-items: center; gap: 4px;
  background: ${theme.citationBg};
  border: 1px solid ${theme.citationBorder};
  color: ${theme.citationText};
  padding: 2px 8px;
  border-radius: 10px;
  font-size: ${font.meta}px;
  line-height: 1.4;
}

.suggested-questions {
  display: flex; flex-wrap: wrap; gap: 6px;
  margin-top: 4px;
}
.suggested-questions button {
  background: transparent;
  border: 1px solid ${theme.themeColor};
  color: ${theme.themeColor};
  padding: 5px 12px;
  border-radius: 999px;
  font-size: ${font.meta}px;
  cursor: pointer;
  font-family: inherit;
  line-height: 1.3;
  transition: background .12s ease;
}
.suggested-questions button:hover {
  background: ${theme.themeColor};
  color: #fff;
}
.suggested-questions button:disabled { opacity: .5; cursor: not-allowed; }

.composer {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid ${theme.borderColor};
  background: ${theme.paneBg};
}
.upload-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  color: ${theme.subtleText};
  padding: 8px;
  border-radius: 8px;
  line-height: 0;
}
.upload-btn:hover { background: rgba(127,127,127,.12); color: ${theme.paneText}; }
.upload-btn svg { width: 16px; height: 16px; }

.composer textarea {
  flex: 1;
  border: 1px solid ${theme.inputBorder};
  background: ${theme.inputBg};
  color: ${theme.paneText};
  border-radius: 10px;
  padding: 8px 10px;
  resize: none;
  font-family: inherit;
  font-size: ${font.panel}px;
  line-height: 1.45;
  max-height: 110px;
  outline: none;
  transition: border-color .15s ease;
}
.composer textarea:focus { border-color: ${theme.inputFocus}; }
.composer textarea:disabled { opacity: .5; cursor: not-allowed; }

.send-btn {
  background: ${theme.themeColor};
  color: #fff;
  border: none;
  border-radius: 10px;
  width: 36px;
  height: 36px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: opacity .15s ease;
}
.send-btn:disabled { opacity: .45; cursor: not-allowed; }
.send-btn svg { width: 16px; height: 16px; }

.brand {
  text-align: center;
  font-size: 11px;
  color: ${theme.brandText};
  padding: 6px 0 8px;
  background: ${theme.brandBg};
  border-top: 1px solid ${theme.borderColor};
}
.brand a { color: inherit; text-decoration: none; }

@media (max-width: 480px) {
  .panel {
    width: calc(100vw - 24px);
    height: calc(100vh - 110px);
  }
  .panel.pos-right-bottom, .panel.pos-left-bottom { bottom: 80px; }
  .panel.pos-right-top, .panel.pos-left-top { top: 80px; }
  .panel.pos-right-bottom, .panel.pos-right-top { right: 12px; }
  .panel.pos-left-bottom, .panel.pos-left-top { left: 12px; }
  .bubble.pos-right-bottom, .bubble.pos-left-bottom { bottom: 16px; }
  .bubble.pos-right-top, .bubble.pos-left-top { top: 16px; }
  .bubble.pos-right-bottom, .bubble.pos-right-top { right: 16px; }
  .bubble.pos-left-bottom, .bubble.pos-left-top { left: 16px; }
}
`;
};

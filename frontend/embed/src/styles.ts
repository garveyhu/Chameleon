/** widget 样式表 —— 注入 shadow DOM 防业务方页面样式污染 */

export const buildStyles = (primary: string): string => `
:host {
  all: initial;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}

* { box-sizing: border-box; }

.bubble {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: ${primary};
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(0,0,0,.15), 0 2px 6px rgba(0,0,0,.1);
  z-index: 2147483647;
  border: none;
  transition: transform .15s ease, box-shadow .15s ease;
}
.bubble:hover { transform: scale(1.06); box-shadow: 0 6px 20px rgba(0,0,0,.18); }
.bubble.left { right: auto; left: 24px; }

.bubble svg { width: 26px; height: 26px; }

.panel {
  position: fixed;
  bottom: 96px;
  right: 24px;
  width: 380px;
  height: 560px;
  max-height: calc(100vh - 120px);
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 12px 40px rgba(0,0,0,.18), 0 4px 12px rgba(0,0,0,.08);
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
.panel.left { right: auto; left: 24px; }

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: ${primary};
  color: #fff;
}
.header-text { flex: 1; min-width: 0; }
.header-title { font-size: 14px; font-weight: 600; line-height: 1.3; }
.header-sub { font-size: 12px; opacity: .85; margin-top: 2px; }
.close-btn {
  background: transparent;
  border: none;
  color: #fff;
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
  background: #f8fafc;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.msg { display: flex; max-width: 85%; }
.msg.user { align-self: flex-end; }
.msg.bot { align-self: flex-start; }

.bubble-text {
  padding: 9px 12px;
  border-radius: 12px;
  font-size: 13.5px;
  line-height: 1.55;
  word-wrap: break-word;
  white-space: pre-wrap;
}
.msg.user .bubble-text {
  background: ${primary};
  color: #fff;
  border-bottom-right-radius: 4px;
}
.msg.bot .bubble-text {
  background: #fff;
  color: #1f2937;
  border: 1px solid #e5e7eb;
  border-bottom-left-radius: 4px;
}
.msg.error .bubble-text {
  background: #fef2f2;
  color: #b91c1c;
  border-color: #fecaca;
}

.typing {
  display: inline-flex;
  gap: 4px;
  padding: 4px 0;
}
.typing span {
  width: 6px; height: 6px; border-radius: 50%;
  background: #9ca3af;
  animation: typing 1.2s infinite ease-in-out;
}
.typing span:nth-child(2) { animation-delay: .15s; }
.typing span:nth-child(3) { animation-delay: .3s; }
@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); opacity: .4; }
  30% { transform: translateY(-4px); opacity: 1; }
}

.composer {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid #e5e7eb;
  background: #fff;
}
.composer textarea {
  flex: 1;
  border: 1px solid #d1d5db;
  border-radius: 10px;
  padding: 8px 10px;
  resize: none;
  font-family: inherit;
  font-size: 13.5px;
  line-height: 1.45;
  max-height: 110px;
  outline: none;
  transition: border-color .15s ease;
}
.composer textarea:focus { border-color: ${primary}; }
.composer textarea:disabled { background: #f3f4f6; cursor: not-allowed; }

.send-btn {
  background: ${primary};
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
  color: #94a3b8;
  padding: 6px 0 8px;
  background: #fff;
  border-top: 1px solid #f1f5f9;
}
.brand a { color: inherit; text-decoration: none; }

.error-banner {
  margin: 10px 16px;
  padding: 8px 12px;
  background: #fef2f2;
  color: #b91c1c;
  border: 1px solid #fecaca;
  border-radius: 8px;
  font-size: 12px;
}

@media (max-width: 480px) {
  .panel {
    width: calc(100vw - 24px);
    height: calc(100vh - 110px);
    right: 12px;
    bottom: 80px;
  }
  .panel.left { left: 12px; }
  .bubble { right: 16px; bottom: 16px; }
  .bubble.left { left: 16px; }
}
`;

/** ChameleonWidget —— shadow DOM 浮动气泡 + 对话面板 */

import { EmbedApi, EmbedError } from './api';
import { chatIcon, closeIcon, sendIcon } from './icons';
import { SessionManager } from './session';
import { buildStyles } from './styles';
import type { EmbedPublicConfig, WidgetMessage, WidgetOptions } from './types';

const DEFAULT_PRIMARY = '#0ea5e9';
const DEFAULT_TITLE = 'Chameleon 助手';

export class ChameleonWidget {
  private opts: WidgetOptions;
  private api: EmbedApi;
  private session: SessionManager;

  private host!: HTMLDivElement;
  private shadow!: ShadowRoot;
  private panel!: HTMLDivElement;
  private bubble!: HTMLButtonElement;
  private messagesEl!: HTMLDivElement;
  private textarea!: HTMLTextAreaElement;
  private sendBtn!: HTMLButtonElement;

  private messages: WidgetMessage[] = [];
  private config: EmbedPublicConfig | null = null;
  private isOpen = false;
  private isSending = false;
  private msgIdSeq = 0;

  constructor(opts: WidgetOptions) {
    this.opts = opts;
    this.api = new EmbedApi(opts.apiBase, opts.embedKey);
    this.session = new SessionManager(this.api);
  }

  async mount(): Promise<void> {
    try {
      this.config = await this.api.getConfig();
    } catch (e) {
      console.error('[ChameleonWidget] 加载配置失败：', e);
      return;
    }

    this.host = document.createElement('div');
    this.host.id = `chameleon-widget-${this.opts.embedKey}`;
    document.body.appendChild(this.host);
    this.shadow = this.host.attachShadow({ mode: 'open' });

    this.renderShell();
    this.bindEvents();
    this.pushWelcomeIfAny();
  }

  destroy(): void {
    this.host?.remove();
  }

  // ─── Render ──────────────────────────────────────────────

  private renderShell(): void {
    const ui = this.config?.ui_config || {};
    const primary = ui.primary_color || DEFAULT_PRIMARY;
    const title = ui.title || this.config?.name || DEFAULT_TITLE;
    const subtitle = ui.subtitle || this.config?.description || '';
    const position = ui.position === 'bottom-left' ? 'left' : '';
    const placeholder = this.config?.behavior?.placeholder || '输入消息……';

    const style = document.createElement('style');
    style.textContent = buildStyles(primary);
    this.shadow.appendChild(style);

    const wrap = document.createElement('div');
    wrap.innerHTML = `
      <button class="bubble ${position}" type="button" aria-label="打开对话">
        ${chatIcon}
      </button>
      <div class="panel ${position}" role="dialog" aria-label="${escapeAttr(title)}">
        <div class="header">
          <div class="header-text">
            <div class="header-title">${escapeText(title)}</div>
            ${subtitle ? `<div class="header-sub">${escapeText(subtitle)}</div>` : ''}
          </div>
          <button class="close-btn" type="button" aria-label="关闭">${closeIcon}</button>
        </div>
        <div class="messages"></div>
        <div class="composer">
          <textarea rows="1" placeholder="${escapeAttr(placeholder)}"></textarea>
          <button class="send-btn" type="button" aria-label="发送">${sendIcon}</button>
        </div>
        <div class="brand">powered by <a href="https://github.com/" target="_blank" rel="noopener">Chameleon</a></div>
      </div>
    `;

    this.shadow.appendChild(wrap);
    this.bubble = this.shadow.querySelector('.bubble') as HTMLButtonElement;
    this.panel = this.shadow.querySelector('.panel') as HTMLDivElement;
    this.messagesEl = this.shadow.querySelector('.messages') as HTMLDivElement;
    this.textarea = this.shadow.querySelector('textarea') as HTMLTextAreaElement;
    this.sendBtn = this.shadow.querySelector('.send-btn') as HTMLButtonElement;
  }

  private bindEvents(): void {
    this.bubble.addEventListener('click', () => this.toggle(true));
    (this.shadow.querySelector('.close-btn') as HTMLButtonElement).addEventListener('click', () =>
      this.toggle(false)
    );
    this.sendBtn.addEventListener('click', () => this.handleSend());
    this.textarea.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.handleSend();
      }
    });
    this.textarea.addEventListener('input', () => {
      this.textarea.style.height = 'auto';
      this.textarea.style.height = Math.min(this.textarea.scrollHeight, 110) + 'px';
    });
  }

  // ─── State ───────────────────────────────────────────────

  private toggle(open?: boolean): void {
    this.isOpen = open ?? !this.isOpen;
    this.panel.classList.toggle('open', this.isOpen);
    if (this.isOpen) {
      setTimeout(() => this.textarea.focus(), 200);
      this.scrollToBottom();
    }
  }

  private pushWelcomeIfAny(): void {
    const welcome = this.config?.welcome_message || this.config?.behavior?.welcome_message;
    if (welcome) {
      this.pushMessage({ id: this.nextId(), role: 'assistant', content: welcome });
    }
  }

  private pushMessage(msg: WidgetMessage): void {
    this.messages.push(msg);
    this.renderMessage(msg);
    this.scrollToBottom();
  }

  private updateMessage(id: string, patch: Partial<WidgetMessage>): void {
    const idx = this.messages.findIndex(m => m.id === id);
    if (idx < 0) return;
    this.messages[idx] = { ...this.messages[idx], ...patch };
    const el = this.messagesEl.querySelector(`[data-mid="${id}"]`);
    if (el) {
      el.replaceWith(this.buildMessageEl(this.messages[idx]));
      this.scrollToBottom();
    }
  }

  private renderMessage(msg: WidgetMessage): void {
    this.messagesEl.appendChild(this.buildMessageEl(msg));
  }

  private buildMessageEl(msg: WidgetMessage): HTMLDivElement {
    const div = document.createElement('div');
    div.className = `msg ${msg.role === 'user' ? 'user' : 'bot'}${msg.error ? ' error' : ''}`;
    div.dataset.mid = msg.id;
    if (msg.pending) {
      div.innerHTML = `<div class="bubble-text"><div class="typing"><span></span><span></span><span></span></div></div>`;
    } else {
      const bubble = document.createElement('div');
      bubble.className = 'bubble-text';
      bubble.textContent = msg.content; // textContent 防 XSS
      div.appendChild(bubble);
    }
    return div;
  }

  private scrollToBottom(): void {
    requestAnimationFrame(() => {
      this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    });
  }

  // ─── Send ────────────────────────────────────────────────

  private async handleSend(): Promise<void> {
    if (this.isSending) return;
    const input = this.textarea.value.trim();
    if (!input) return;

    this.isSending = true;
    this.textarea.value = '';
    this.textarea.style.height = 'auto';
    this.setComposerDisabled(true);

    this.pushMessage({ id: this.nextId(), role: 'user', content: input });
    const pendingId = this.nextId();
    this.pushMessage({ id: pendingId, role: 'assistant', content: '', pending: true });

    try {
      const res = await this.session.invokeWithRetry(input);
      this.updateMessage(pendingId, { content: res.answer, pending: false });
    } catch (e) {
      const msg = e instanceof EmbedError ? e.message : '调用失败，请稍后重试';
      this.updateMessage(pendingId, { content: msg, pending: false, error: true });
    } finally {
      this.isSending = false;
      this.setComposerDisabled(false);
      this.textarea.focus();
    }
  }

  private setComposerDisabled(disabled: boolean): void {
    this.textarea.disabled = disabled;
    this.sendBtn.disabled = disabled;
  }

  private nextId(): string {
    return `m${++this.msgIdSeq}`;
  }
}

// ─── helpers ─────────────────────────────────────────────────

function escapeAttr(s: string): string {
  return s.replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

function escapeText(s: string): string {
  return s.replace(/[<>&"']/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&#39;' }[c] || c));
}

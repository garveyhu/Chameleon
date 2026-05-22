/** ChameleonWidget —— shadow DOM 浮动气泡 + 对话面板
 *
 * 视觉 / 行为完全由 admin 端 ui_config + behavior 驱动；本类只负责把字段渲染出来。
 */

import { EmbedApi, EmbedError } from './api';
import {
  closeIcon,
  getBubbleIcon,
  paperclipIcon,
  sendIcon,
  thumbsDownIcon,
  thumbsUpIcon,
} from './icons';
import { renderMarkdown } from './markdown';
import { SessionManager } from './session';
import { buildStyles } from './styles';
import type {
  BehaviorConfig,
  BubblePosition,
  EmbedPublicConfig,
  StreamChunk,
  UiConfig,
  WidgetMessage,
  WidgetOptions,
} from './types';

const DEFAULT_TITLE = 'Chameleon 助手';
const DEFAULT_GREETING = '';
const DEFAULT_PLACEHOLDER = '请输入你的问题…';

const DEFAULT_UI: Required<UiConfig> = {
  theme_color: '#2563EB',
  icon_emoji: '🤖',
  title: DEFAULT_TITLE,
  subtitle: '',
  greeting: DEFAULT_GREETING,
  placeholder: DEFAULT_PLACEHOLDER,
  bubble_position: 'right-bottom',
  bubble_color: '#2563EB',
  bubble_icon: 'chat',
  mode: 'light',
  border_radius: 12,
  font_size: 'md',
  panel_width: 400,
  panel_height: 600,
  header_bg: '#2563EB',
  shadow: 'lg',
};

const DEFAULT_BEHAVIOR: Required<BehaviorConfig> = {
  auto_open: false,
  auto_open_delay_ms: 0,
  suggested_questions: [],
  show_feedback: true,
  show_citations: true,
  allow_file_upload: false,
  streaming: true,
};

function mergeUi(raw: UiConfig | null | undefined): Required<UiConfig> {
  return { ...DEFAULT_UI, ...(raw || {}) };
}
function mergeBehavior(raw: BehaviorConfig | null | undefined): Required<BehaviorConfig> {
  return { ...DEFAULT_BEHAVIOR, ...(raw || {}) };
}

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

  private config: EmbedPublicConfig | null = null;
  private ui: Required<UiConfig> = DEFAULT_UI;
  private behavior: Required<BehaviorConfig> = DEFAULT_BEHAVIOR;
  private messages: WidgetMessage[] = [];
  private isOpen = false;
  private isSending = false;
  private msgIdSeq = 0;
  private currentAbort: AbortController | null = null;

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
    this.ui = mergeUi(this.config.ui_config);
    this.behavior = mergeBehavior(this.config.behavior);

    this.host = document.createElement('div');
    this.host.id = `chameleon-widget-${this.opts.embedKey}`;
    document.body.appendChild(this.host);
    this.shadow = this.host.attachShadow({ mode: 'open' });

    this.renderShell();
    this.bindEvents();
    this.pushGreetingIfAny();

    if (this.behavior.auto_open) {
      const delay = Math.max(0, this.behavior.auto_open_delay_ms ?? 0);
      window.setTimeout(() => this.toggle(true), delay);
    }
  }

  destroy(): void {
    this.currentAbort?.abort();
    this.host?.remove();
  }

  // ─── Render ──────────────────────────────────────────────

  private renderShell(): void {
    const ui = this.ui;
    const pos: BubblePosition = ui.bubble_position;
    const title = ui.title || this.config?.name || DEFAULT_TITLE;
    const subtitle = ui.subtitle || this.config?.description || '';
    const placeholder = ui.placeholder || DEFAULT_PLACEHOLDER;

    const style = document.createElement('style');
    style.textContent = buildStyles(ui);
    this.shadow.appendChild(style);

    const wrap = document.createElement('div');
    wrap.innerHTML = `
      <button class="bubble pos-${pos}" type="button" aria-label="${escapeAttr(title)}">
        ${getBubbleIcon(ui.bubble_icon)}
      </button>
      <div class="panel pos-${pos}" role="dialog" aria-label="${escapeAttr(title)}">
        <div class="header">
          <div class="header-main">
            ${ui.icon_emoji ? `<span class="header-emoji">${escapeText(ui.icon_emoji)}</span>` : ''}
            <div class="header-text">
              <div class="header-title">${escapeText(title)}</div>
              ${subtitle ? `<div class="header-sub">${escapeText(subtitle)}</div>` : ''}
            </div>
          </div>
          <button class="close-btn" type="button" aria-label="关闭">${closeIcon}</button>
        </div>
        <div class="messages"></div>
        <div class="composer">
          ${this.behavior.allow_file_upload ? `<button class="upload-btn" type="button" aria-label="上传附件">${paperclipIcon}</button>` : ''}
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
    this.bubble.addEventListener('click', () => this.toggle());
    (this.shadow.querySelector('.close-btn') as HTMLButtonElement).addEventListener(
      'click',
      () => this.toggle(false),
    );
    this.sendBtn.addEventListener('click', () => this.handleSend(this.textarea.value.trim()));
    this.textarea.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.handleSend(this.textarea.value.trim());
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

  private pushGreetingIfAny(): void {
    const greeting = this.ui.greeting;
    if (!greeting) {
      this.renderSuggestedQuestionsIfAny();
      return;
    }
    this.pushMessage({ id: this.nextId(), role: 'assistant', content: greeting });
    this.renderSuggestedQuestionsIfAny();
  }

  private renderSuggestedQuestionsIfAny(): void {
    const qs = this.behavior.suggested_questions || [];
    if (qs.length === 0) return;
    const wrap = document.createElement('div');
    wrap.className = 'suggested-questions';
    wrap.dataset.role = 'suggested';
    for (const q of qs) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = q;
      btn.addEventListener('click', () => {
        wrap.remove();
        this.handleSend(q);
      });
      wrap.appendChild(btn);
    }
    this.messagesEl.appendChild(wrap);
    this.scrollToBottom();
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
    const wrap = document.createElement('div');
    wrap.className = `msg ${msg.role === 'user' ? 'user' : 'bot'}${msg.error ? ' error' : ''}`;
    wrap.dataset.mid = msg.id;

    if (msg.role === 'assistant' && this.ui.icon_emoji) {
      const avatar = document.createElement('span');
      avatar.className = 'avatar';
      avatar.textContent = this.ui.icon_emoji;
      wrap.appendChild(avatar);
    }

    const inner = document.createElement('div');
    inner.style.minWidth = '0';
    inner.style.maxWidth = '100%';

    const bubble = document.createElement('div');
    bubble.className = 'bubble-text';
    if (msg.pending && !msg.content) {
      bubble.innerHTML = `<div class="typing"><span></span><span></span><span></span></div>`;
    } else if (msg.role === 'assistant') {
      bubble.innerHTML = renderMarkdown(msg.content);
    } else {
      // user 不解析 markdown，避免误识别
      bubble.textContent = msg.content;
    }
    inner.appendChild(bubble);

    if (msg.role === 'assistant' && !msg.pending && !msg.error) {
      if (this.behavior.show_citations && msg.citations && msg.citations.length > 0) {
        const c = document.createElement('div');
        c.className = 'citations';
        for (const cit of msg.citations) {
          const chip = document.createElement('span');
          chip.className = 'citation-chip';
          chip.textContent = `📎 ${cit.title || cit.source || '引用'}`;
          if (cit.snippet) chip.title = cit.snippet;
          c.appendChild(chip);
        }
        inner.appendChild(c);
      }
      if (this.behavior.show_feedback && !msg.streaming) {
        inner.appendChild(this.buildFeedbackTools(msg));
      }
    }

    wrap.appendChild(inner);
    return wrap;
  }

  private buildFeedbackTools(msg: WidgetMessage): HTMLDivElement {
    const tools = document.createElement('div');
    tools.className = 'msg-tools';
    const up = document.createElement('button');
    up.type = 'button';
    up.title = '有帮助';
    up.innerHTML = thumbsUpIcon;
    const down = document.createElement('button');
    down.type = 'button';
    down.title = '没帮助';
    down.innerHTML = thumbsDownIcon;
    if (msg.feedback === 1) up.classList.add('active');
    if (msg.feedback === -1) down.classList.add('active');

    // 没有 requestId（极少数后端老分支 / 错误响应）→ 禁用反馈按钮
    if (!msg.requestId) {
      up.disabled = true;
      down.disabled = true;
      tools.appendChild(up);
      tools.appendChild(down);
      return tools;
    }

    const submit = (positive: boolean, btn: HTMLButtonElement) => {
      const other = positive ? down : up;
      // 二次点击同一个 = 撤销（视为新反馈值的语义；当前后端 append-only，简化为：始终发送一条 score）
      const willActive = !btn.classList.contains('active');
      btn.classList.toggle('active', willActive);
      other.classList.remove('active');
      const value: 1 | -1 | null = willActive ? (positive ? 1 : -1) : null;
      this.updateMessage(msg.id, { feedback: value });
      if (willActive && msg.requestId) {
        void this.api.feedback({
          trace_id: msg.requestId,
          name: 'thumbs',
          value: positive ? 1 : -1,
        });
      }
    };
    up.addEventListener('click', () => submit(true, up));
    down.addEventListener('click', () => submit(false, down));
    tools.appendChild(up);
    tools.appendChild(down);
    return tools;
  }

  private scrollToBottom(): void {
    requestAnimationFrame(() => {
      this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    });
  }

  // ─── Send ────────────────────────────────────────────────

  private async handleSend(input: string): Promise<void> {
    if (this.isSending) return;
    const trimmed = input.trim();
    if (!trimmed) return;
    if (!this.isOpen) this.toggle(true);

    this.isSending = true;
    this.textarea.value = '';
    this.textarea.style.height = 'auto';
    this.setComposerDisabled(true);

    // 清掉首屏的推荐问题面板（点击后已发，留着没意义）
    this.messagesEl.querySelector('.suggested-questions[data-role="suggested"]')?.remove();

    this.pushMessage({ id: this.nextId(), role: 'user', content: trimmed });
    const pendingId = this.nextId();
    this.pushMessage({
      id: pendingId,
      role: 'assistant',
      content: '',
      pending: true,
      streaming: this.behavior.streaming,
    });

    try {
      if (this.behavior.streaming) {
        await this.runStream(pendingId, trimmed);
      } else {
        await this.runOneShot(pendingId, trimmed);
      }
    } catch (e) {
      const msg = e instanceof EmbedError ? e.message : '调用失败，请稍后重试';
      this.updateMessage(pendingId, {
        content: msg,
        pending: false,
        streaming: false,
        error: true,
      });
    } finally {
      this.isSending = false;
      this.setComposerDisabled(false);
      this.textarea.focus();
    }
  }

  private async runOneShot(pendingId: string, input: string): Promise<void> {
    const res = await this.session.invokeWithRetry(input);
    this.updateMessage(pendingId, {
      content: res.answer,
      requestId: res.request_id ?? undefined,
      pending: false,
      streaming: false,
    });
  }

  private async runStream(pendingId: string, input: string): Promise<void> {
    const ctrl = new AbortController();
    this.currentAbort = ctrl;
    let buf = '';
    let requestId: string | undefined;
    const citations: { title?: string; source?: string; snippet?: string }[] = [];
    let errorChunk: { type: string; message: string } | null = null;

    try {
      await this.session.streamWithRetry(
        input,
        (chunk: StreamChunk) => {
          if (chunk.error) {
            errorChunk = chunk.error;
            return;
          }
          if (chunk.meta?.request_id) {
            requestId = chunk.meta.request_id;
          }
          if (chunk.delta) {
            buf += chunk.delta;
            this.updateMessage(pendingId, {
              content: buf,
              pending: false,
              streaming: true,
            });
          }
          if (chunk.citation) {
            citations.push({
              title: typeof chunk.citation.title === 'string' ? chunk.citation.title : undefined,
              source: typeof chunk.citation.source === 'string' ? chunk.citation.source : undefined,
              snippet:
                typeof chunk.citation.snippet === 'string' ? chunk.citation.snippet : undefined,
            });
          }
          if (chunk.end) {
            this.updateMessage(pendingId, {
              content: chunk.answer || buf,
              citations: citations.length ? citations : undefined,
              requestId,
              pending: false,
              streaming: false,
            });
          }
        },
        ctrl.signal,
      );
    } finally {
      this.currentAbort = null;
    }

    if (errorChunk) {
      const e = errorChunk as { type: string; message: string };
      this.updateMessage(pendingId, {
        content: `${e.type}: ${e.message}`,
        pending: false,
        streaming: false,
        error: true,
      });
    } else if (buf && !this.messages.find(m => m.id === pendingId && !m.streaming)) {
      // 万一 end 没到，把累积的内容收尾
      this.updateMessage(pendingId, {
        content: buf,
        citations: citations.length ? citations : undefined,
        requestId,
        pending: false,
        streaming: false,
      });
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
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

function escapeText(s: string): string {
  return s.replace(
    /[<>&"']/g,
    c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&#39;' })[c] || c,
  );
}

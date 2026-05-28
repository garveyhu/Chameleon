/** ChameleonWidget —— shadow DOM 浮动气泡 + 对话面板
 *
 * 视觉 / 行为完全由 admin 端 ui_config + behavior 驱动；本类只负责把字段渲染出来。
 */

import { EmbedApi, EmbedError } from './api';
import {
  checkIcon,
  closeIcon,
  copyIcon,
  editIcon,
  getBubbleIcon,
  menuIcon,
  moreIcon,
  paperclipIcon,
  plusIcon,
  refreshIcon,
  sendIcon,
  thumbsDownIcon,
  thumbsUpIcon,
  trashIcon,
} from './icons';
import { renderMarkdown } from './markdown';
import { SessionManager } from './session';
import { buildStyles } from './styles';
import type {
  BehaviorConfig,
  BubblePosition,
  EmbedMessageItem,
  EmbedPublicConfig,
  EmbedSessionItem,
  StreamChunk,
  UiConfig,
  WidgetAttachment,
  WidgetMessage,
  WidgetOptions,
} from './types';

const DEFAULT_TITLE = 'Chameleon 助手';
const DEFAULT_GREETING = '';
const DEFAULT_PLACEHOLDER = '请输入你的问题…';

const DEFAULT_UI: Required<UiConfig> = {
  theme_color: '#2563EB',
  icon_url: null,
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
  show_followups: false,
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
  private sidebarListEl: HTMLDivElement | null = null;

  private config: EmbedPublicConfig | null = null;
  private ui: Required<UiConfig> = DEFAULT_UI;
  private behavior: Required<BehaviorConfig> = DEFAULT_BEHAVIOR;
  private messages: WidgetMessage[] = [];
  private isOpen = false;
  private isSending = false;
  private msgIdSeq = 0;
  private currentAbort: AbortController | null = null;
  // 侧栏 / 续接状态
  private sessions: EmbedSessionItem[] = [];
  private currentSessionId: string | null = null;
  private sidebarOpen = false;
  // Phase A 附件：等待发送的已上传文件
  private pendingAttachments: WidgetAttachment[] = [];
  private fileInputEl: HTMLInputElement | null = null;
  private attachmentChipsEl: HTMLDivElement | null = null;

  constructor(opts: WidgetOptions) {
    this.opts = opts;
    this.api = new EmbedApi(opts.apiBase, opts.embedKey);
    this.session = new SessionManager(this.api, opts.embedKey, {
      externalUserId: opts.externalUserId,
      jwtToken: opts.jwtToken,
    });
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

    // 模式 vs 业务方传入的身份匹配性检查 —— 不匹配直接显错并禁用输入
    const policyErr = this.checkIdentityAgainstPolicy();
    if (policyErr) {
      this.pushMessage({
        id: this.nextId(),
        role: 'assistant',
        content: policyErr,
        error: true,
      });
      this.setComposerDisabled(true);
    } else {
      // 续接 / 招呼语：受 session_policy.auto_resume_last 控制
      const resumed = await this.tryAutoResume();
      if (!resumed) {
        this.pushGreetingIfAny();
      }
      // 后台拉历史会话列表（受 show_history_sidebar 控制；失败静默）
      this.hydrateSessions().catch(err =>
        console.warn('[ChameleonWidget] sessions hydrate failed', err),
      );
    }

    if (this.behavior.auto_open) {
      const delay = Math.max(0, this.behavior.auto_open_delay_ms ?? 0);
      window.setTimeout(() => this.toggle(true), delay);
    }
  }

  /** localStorage 上次会话 sid（按 embed_key 隔离） */
  private get lastSidKey(): string {
    return `chameleon-embed:last-sid:${this.opts.embedKey}`;
  }
  private rememberSid(sid: string | null): void {
    try {
      if (sid) localStorage.setItem(this.lastSidKey, sid);
      else localStorage.removeItem(this.lastSidKey);
    } catch {
      /* localStorage 不可用，忽略 */
    }
  }

  /** 续接策略：policy.auto_resume_last=true 且 localStorage 有 sid → 拉消息渲到面板
   *  GET /sessions/{sid}/messages 端点同时会 rebind token sid（隐式 side-effect），
   *  所以拉完 messages 后下一条 invoke 自动落入老会话。 */
  private async tryAutoResume(): Promise<boolean> {
    const policy = this.config?.session_policy;
    if (!policy?.auto_resume_last) return false;
    let sid: string | null = null;
    try {
      sid = localStorage.getItem(this.lastSidKey);
    } catch {
      return false;
    }
    if (!sid) return false;
    try {
      await this.switchToSession(sid, { silent: true });
      return this.messages.length > 0;
    } catch (e) {
      console.warn('[ChameleonWidget] resume failed', e);
      this.rememberSid(null);
      return false;
    }
  }

  /** 切到某历史会话：拉消息渲到面板 + 更新 currentSessionId + 侧栏高亮
   *  silent=true：失败不报错（用于 auto-resume 兜底） */
  private async switchToSession(sid: string, opts?: { silent?: boolean }): Promise<void> {
    try {
      const token = await this.session.getToken();
      const msgs = await this.api.listMessages(token, sid);
      this.currentSessionId = sid;
      this.rememberSid(sid);
      this.messages = msgs.map(m => this.adaptHistoryMessage(m));
      this.repaintMessages();
      this.refreshSidebarHighlight();
    } catch (e) {
      if (opts?.silent) throw e;
      const msg = e instanceof EmbedError ? e.message : '加载会话失败';
      this.pushMessage({
        id: this.nextId(),
        role: 'assistant',
        content: msg,
        error: true,
      });
    }
  }

  /** 历史消息 → widget 消息格式 */
  private adaptHistoryMessage(m: EmbedMessageItem): WidgetMessage {
    // 从 content_blocks 提取 image/audio_url block → WidgetAttachment[]
    let attachments: WidgetAttachment[] | undefined;
    if (m.content_blocks && m.content_blocks.length) {
      const atts: WidgetAttachment[] = [];
      for (const b of m.content_blocks) {
        if (b.type === 'image_url') {
          const url = (b as { image_url?: { url?: string } }).image_url?.url;
          if (url) {
            atts.push({
              object_url: url,
              filename: '',
              mime: 'image/*',
              size: 0,
              kind: 'image',
            });
          }
        } else if (b.type === 'audio_url') {
          const url = (b as { audio_url?: { url?: string } }).audio_url?.url;
          if (url) {
            atts.push({
              object_url: url,
              filename: '',
              mime: 'audio/*',
              size: 0,
              kind: 'audio',
            });
          }
        }
      }
      if (atts.length) attachments = atts;
    }
    return {
      id: String(m.id ?? this.nextId()),
      role: m.role,
      content: m.content,
      citations: m.citations,
      attachments,
    };
  }

  /** 把 this.messages 整体重渲到 messagesEl（切会话用） */
  private repaintMessages(): void {
    this.messagesEl.innerHTML = '';
    for (const m of this.messages) {
      this.renderMessage(m);
    }
    this.scrollToBottom();
  }

  /** 后台拉历史会话列表 + 渲到侧栏（受 show_history_sidebar 控制） */
  private async hydrateSessions(): Promise<void> {
    if (!this.config?.session_policy?.show_history_sidebar) return;
    const token = await this.session.getToken();
    this.sessions = await this.api.listSessions(token);
    this.renderSidebarList();
  }

  /** 开新对话：调端点切 sid，清面板，重渲招呼 */
  private async openNewSession(): Promise<void> {
    try {
      const token = await this.session.getToken();
      const res = await this.api.createNewSession(token);
      this.currentSessionId = res.session_id;
      this.rememberSid(res.session_id);
      this.messages = [];
      this.repaintMessages();
      this.pushGreetingIfAny();
      // 列表里这个新 sid 还没消息，先不插条目；hydrate 等首条消息后再刷
      this.refreshSidebarHighlight();
    } catch (e) {
      console.warn('[ChameleonWidget] new session failed', e);
    }
  }

  private toggleSidebar(open?: boolean): void {
    this.sidebarOpen = open ?? !this.sidebarOpen;
    this.panel.classList.toggle('sidebar-open', this.sidebarOpen);
  }

  /** 后端策略 ↔ 接入方传入字段匹配性检查；不匹配返人类可读错误 */
  private checkIdentityAgainstPolicy(): string | null {
    const mode = this.config?.session_policy?.identification_mode;
    if (mode === 'external_user_id' && !this.opts.externalUserId) {
      return '该嵌入式应用配置为「外部用户 ID」模式，但页面未传入 externalUserId。请联系网站管理员。';
    }
    if (mode === 'signed_jwt' && !this.opts.jwtToken) {
      return '该嵌入式应用配置为「签名 JWT」模式，但页面未传入 jwtToken。请联系网站管理员。';
    }
    return null;
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
    const showSidebar = !!this.config?.session_policy?.show_history_sidebar;

    const style = document.createElement('style');
    style.textContent = buildStyles(ui);
    this.shadow.appendChild(style);

    const sidebarHtml = showSidebar
      ? `
        <aside class="sidebar" aria-hidden="true">
          <div class="sidebar-head">
            <div class="sidebar-title">历史记录</div>
            <div class="sidebar-head-actions">
              <button class="new-session-btn" type="button">
                ${plusIcon}<span>新对话</span>
              </button>
              <button class="sidebar-close" type="button" aria-label="关闭">${closeIcon}</button>
            </div>
          </div>
          <div class="sidebar-list" role="list"></div>
        </aside>
      `
      : '';

    const wrap = document.createElement('div');
    wrap.innerHTML = `
      <button class="bubble pos-${pos}" type="button" aria-label="${escapeAttr(title)}">
        ${getBubbleIcon(ui.bubble_icon)}
      </button>
      <div class="panel pos-${pos}${showSidebar ? ' has-sidebar' : ''}" role="dialog" aria-label="${escapeAttr(title)}">
        <div class="header">
          <div class="header-main">
            ${
              showSidebar
                ? `<button class="sidebar-toggle" type="button" title="历史会话">${menuIcon}</button>`
                : ''
            }
            ${
              ui.icon_url
                ? `<span class="header-emoji"><img src="${escapeAttr(ui.icon_url)}" alt=""></span>`
                : ui.icon_emoji
                  ? `<span class="header-emoji">${escapeText(ui.icon_emoji)}</span>`
                  : ''
            }
            <div class="header-text">
              <div class="header-title">${escapeText(title)}</div>
              ${subtitle ? `<div class="header-sub">${escapeText(subtitle)}</div>` : ''}
            </div>
          </div>
          <button class="close-btn" type="button" aria-label="关闭">${closeIcon}</button>
        </div>
        <div class="messages"></div>
        ${this.behavior.allow_file_upload ? '<div class="attachment-chips" hidden></div>' : ''}
        <div class="composer">
          ${this.behavior.allow_file_upload ? `<button class="upload-btn" type="button" aria-label="上传附件">${paperclipIcon}</button>` : ''}
          ${this.behavior.allow_file_upload ? '<input class="file-input" type="file" multiple hidden accept="image/*,audio/*,application/pdf,text/plain,text/markdown,.md,.docx,.csv,.xlsx"/>' : ''}
          <textarea rows="1" placeholder="${escapeAttr(placeholder)}"></textarea>
          <button class="send-btn" type="button" aria-label="发送">${sendIcon}</button>
        </div>
        <div class="brand">powered by <a href="https://github.com/" target="_blank" rel="noopener">Chameleon</a></div>
        ${sidebarHtml}
      </div>
    `;

    this.shadow.appendChild(wrap);
    this.bubble = this.shadow.querySelector('.bubble') as HTMLButtonElement;
    this.panel = this.shadow.querySelector('.panel') as HTMLDivElement;
    this.messagesEl = this.shadow.querySelector('.messages') as HTMLDivElement;
    this.textarea = this.shadow.querySelector('textarea') as HTMLTextAreaElement;
    this.sendBtn = this.shadow.querySelector('.send-btn') as HTMLButtonElement;
    if (showSidebar) {
      this.sidebarListEl = this.shadow.querySelector('.sidebar-list') as HTMLDivElement;
    }
    if (this.behavior.allow_file_upload) {
      this.attachmentChipsEl = this.shadow.querySelector('.attachment-chips') as HTMLDivElement;
      this.fileInputEl = this.shadow.querySelector('.file-input') as HTMLInputElement;
    }
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
    // 侧栏相关 —— 没渲就略过
    const sidebarToggle = this.shadow.querySelector('.sidebar-toggle') as HTMLButtonElement | null;
    sidebarToggle?.addEventListener('click', () => this.toggleSidebar());
    const sidebarClose = this.shadow.querySelector('.sidebar-close') as HTMLButtonElement | null;
    sidebarClose?.addEventListener('click', () => this.toggleSidebar(false));
    const newBtn = this.shadow.querySelector('.new-session-btn') as HTMLButtonElement | null;
    newBtn?.addEventListener('click', () => {
      void this.openNewSession();
      this.toggleSidebar(false);
    });

    // 附件上传（受 allow_file_upload 控制）
    const uploadBtn = this.shadow.querySelector('.upload-btn') as HTMLButtonElement | null;
    uploadBtn?.addEventListener('click', () => this.fileInputEl?.click());
    this.fileInputEl?.addEventListener('change', () => {
      const files = Array.from(this.fileInputEl?.files ?? []);
      if (this.fileInputEl) this.fileInputEl.value = ''; // 允许再选同名
      if (files.length) void this.handleFilesPicked(files);
    });
  }

  // ─── 附件上传 ───────────────────────────────────────────

  private async handleFilesPicked(files: File[]): Promise<void> {
    // 单次上传上限：5 个 / 单文件 ≤ 20MB
    const MAX_FILES = 5;
    const MAX_BYTES = 20 * 1024 * 1024;
    const picked = files.slice(0, MAX_FILES);
    const oversize = picked.filter(f => f.size > MAX_BYTES);
    if (oversize.length) {
      this.pushTransientNotice(
        `文件超过 20MB 限制：${oversize.map(f => f.name).join(', ')}`,
        true,
      );
      return;
    }
    // 给每个文件先插占位 chip（status=uploading）
    const placeholders = picked.map(f => {
      const att: WidgetAttachment = {
        object_url: '',
        filename: f.name,
        mime: f.type || 'application/octet-stream',
        size: f.size,
        kind: 'other',
      };
      return { file: f, att };
    });
    for (const { att } of placeholders) {
      this.pendingAttachments.push(att);
    }
    this.renderAttachmentChips();

    // 并发上传
    await Promise.all(
      placeholders.map(async ({ file, att }) => {
        try {
          const uploaded = await this.api.uploadFile(file);
          // 用真实 attachment 替换占位
          Object.assign(att, uploaded);
        } catch (e) {
          console.warn('[ChameleonWidget] upload failed', e);
          this.pendingAttachments = this.pendingAttachments.filter(a => a !== att);
          this.pushTransientNotice(`上传失败：${file.name}`, true);
        }
      }),
    );
    this.renderAttachmentChips();
  }

  private removeAttachment(att: WidgetAttachment): void {
    this.pendingAttachments = this.pendingAttachments.filter(a => a !== att);
    this.renderAttachmentChips();
  }

  private renderAttachmentChips(): void {
    const el = this.attachmentChipsEl;
    if (!el) return;
    el.innerHTML = '';
    if (!this.pendingAttachments.length) {
      el.setAttribute('hidden', '');
      return;
    }
    el.removeAttribute('hidden');
    for (const att of this.pendingAttachments) {
      const chip = document.createElement('div');
      chip.className = 'att-chip';
      const isImage = att.mime.startsWith('image/');
      const uploading = !att.object_url;
      chip.innerHTML = `
        ${
          isImage && att.object_url
            ? `<img src="${escapeAttr(att.object_url)}" alt="">`
            : `<span class="att-chip-icon">${uploading ? '⏳' : '📎'}</span>`
        }
        <span class="att-chip-name" title="${escapeAttr(att.filename)}">${escapeText(att.filename)}</span>
        <button type="button" class="att-chip-remove" aria-label="移除">×</button>
      `;
      const removeBtn = chip.querySelector('.att-chip-remove') as HTMLButtonElement;
      removeBtn.addEventListener('click', () => this.removeAttachment(att));
      el.appendChild(chip);
    }
  }

  private pushTransientNotice(text: string, error = false): void {
    this.pushMessage({
      id: this.nextId(),
      role: 'assistant',
      content: text,
      error,
    });
  }

  /** 把 this.sessions 重绘到侧栏列表 */
  private renderSidebarList(): void {
    if (!this.sidebarListEl) return;
    this.sidebarListEl.innerHTML = '';
    if (!this.sessions.length) {
      const empty = document.createElement('div');
      empty.className = 'sidebar-empty';
      empty.textContent = '暂无历史会话';
      this.sidebarListEl.appendChild(empty);
      return;
    }
    const allowManage = !!this.config?.session_policy?.allow_user_manage;
    for (const s of this.sessions) {
      this.sidebarListEl.appendChild(this.buildSidebarItem(s, allowManage));
    }
    this.refreshSidebarHighlight();
  }

  /** 切换/新建/删除后只更新高亮，不重绘整列表 */
  private refreshSidebarHighlight(): void {
    if (!this.sidebarListEl) return;
    this.sidebarListEl.querySelectorAll('.sidebar-item').forEach(el => {
      const sid = (el as HTMLElement).dataset.sid;
      el.classList.toggle('active', sid === this.currentSessionId);
    });
  }

  private buildSidebarItem(s: EmbedSessionItem, allowManage: boolean): HTMLDivElement {
    const wrap = document.createElement('div');
    wrap.className = 'sidebar-item';
    wrap.dataset.sid = s.session_id;

    // 圆形 avatar：复用 UI 配置的头像（icon_url > icon_emoji > 默认）
    const avatar = document.createElement('span');
    avatar.className = 'sidebar-item-avatar';
    if (this.ui.icon_url) {
      const img = document.createElement('img');
      img.src = this.ui.icon_url;
      img.alt = '';
      avatar.appendChild(img);
    } else {
      avatar.textContent = this.ui.icon_emoji || '💬';
    }
    wrap.appendChild(avatar);

    const titleEl = document.createElement('div');
    titleEl.className = 'sidebar-item-title';
    titleEl.textContent = s.title || '新对话';
    wrap.appendChild(titleEl);

    const timeEl = document.createElement('span');
    timeEl.className = 'sidebar-item-time';
    timeEl.textContent = formatRelativeTime(s.last_message_at ?? s.created_at);
    wrap.appendChild(timeEl);

    if (allowManage) {
      const menu = document.createElement('div');
      menu.className = 'sidebar-item-menu';
      menu.innerHTML = `<button class="sidebar-item-more" type="button" aria-label="更多">${moreIcon}</button>`;
      menu.addEventListener('click', e => {
        e.stopPropagation();
        this.openItemMenu(wrap, s);
      });
      wrap.appendChild(menu);
    }

    wrap.addEventListener('click', () => {
      if (s.session_id === this.currentSessionId) {
        this.toggleSidebar(false);
        return;
      }
      void this.switchToSession(s.session_id);
      this.toggleSidebar(false);
    });
    return wrap;
  }

  /** 三点菜单：内联展开「改名 / 删除」两个按钮 */
  private openItemMenu(itemEl: HTMLDivElement, s: EmbedSessionItem): void {
    // 先关掉别处可能开着的菜单
    this.shadow.querySelectorAll('.sidebar-item-pop').forEach(n => n.remove());
    const pop = document.createElement('div');
    pop.className = 'sidebar-item-pop';
    pop.innerHTML = `
      <button type="button" data-act="rename">${editIcon}<span>改名</span></button>
      <button type="button" data-act="delete" class="danger">${trashIcon}<span>删除</span></button>
    `;
    pop.addEventListener('click', e => {
      const target = (e.target as HTMLElement).closest('[data-act]') as HTMLElement | null;
      if (!target) return;
      e.stopPropagation();
      pop.remove();
      const act = target.dataset.act;
      if (act === 'rename') this.startInlineRename(itemEl, s);
      else if (act === 'delete') this.confirmAndDelete(itemEl, s);
    });
    itemEl.appendChild(pop);
    // 点别处关掉
    const off = (e: MouseEvent) => {
      if (!pop.contains(e.target as Node)) {
        pop.remove();
        this.shadow.removeEventListener('click', off as EventListener, true);
      }
    };
    // 用 capture 在 shadow 里抓
    setTimeout(() => this.shadow.addEventListener('click', off as EventListener, true), 0);
  }

  /** 把 sidebar-item-title 替换成 input，inline 编辑 */
  private startInlineRename(itemEl: HTMLDivElement, s: EmbedSessionItem): void {
    const titleEl = itemEl.querySelector('.sidebar-item-title') as HTMLDivElement;
    const input = document.createElement('input');
    input.className = 'sidebar-item-edit';
    input.value = s.title || '';
    input.placeholder = '会话名称';
    titleEl.replaceWith(input);
    input.focus();
    input.select();

    const cancel = () => {
      const restored = document.createElement('div');
      restored.className = 'sidebar-item-title';
      restored.textContent = s.title || '新对话';
      input.replaceWith(restored);
    };
    const commit = async () => {
      const next = input.value.trim();
      if (!next || next === s.title) {
        cancel();
        return;
      }
      try {
        const token = await this.session.getToken();
        const updated = await this.api.renameSession(token, s.session_id, next);
        s.title = updated.title;
        const restored = document.createElement('div');
        restored.className = 'sidebar-item-title';
        restored.textContent = s.title || '新对话';
        input.replaceWith(restored);
      } catch (e) {
        console.warn('[ChameleonWidget] rename failed', e);
        cancel();
      }
    };
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        void commit();
      } else if (e.key === 'Escape') {
        cancel();
      }
    });
    input.addEventListener('blur', () => void commit());
  }

  /** 删除：在 item 内 inline 二次确认（不弹原生 confirm，避免阻塞事件） */
  private confirmAndDelete(itemEl: HTMLDivElement, s: EmbedSessionItem): void {
    this.shadow.querySelectorAll('.sidebar-item-confirm').forEach(n => n.remove());
    const bar = document.createElement('div');
    bar.className = 'sidebar-item-confirm';
    bar.innerHTML = `
      <span>确定删除？</span>
      <button type="button" data-act="ok" class="danger">删除</button>
      <button type="button" data-act="no">取消</button>
    `;
    bar.addEventListener('click', async e => {
      e.stopPropagation();
      const act = (e.target as HTMLElement).closest('[data-act]')?.getAttribute('data-act');
      if (act === 'no') {
        bar.remove();
      } else if (act === 'ok') {
        bar.remove();
        try {
          const token = await this.session.getToken();
          await this.api.deleteSession(token, s.session_id);
          this.sessions = this.sessions.filter(x => x.session_id !== s.session_id);
          this.renderSidebarList();
          // 删的就是当前会话 → 自动开新对话
          if (s.session_id === this.currentSessionId) {
            await this.openNewSession();
          }
        } catch (err) {
          console.warn('[ChameleonWidget] delete failed', err);
        }
      }
    });
    itemEl.appendChild(bar);
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

    if (msg.role === 'assistant' && (this.ui.icon_url || this.ui.icon_emoji)) {
      const avatar = document.createElement('span');
      avatar.className = 'avatar';
      if (this.ui.icon_url) {
        const img = document.createElement('img');
        img.src = this.ui.icon_url;
        img.alt = '';
        avatar.appendChild(img);
      } else {
        avatar.textContent = this.ui.icon_emoji;
      }
      wrap.appendChild(avatar);
    }

    const inner = document.createElement('div');
    inner.style.minWidth = '0';
    inner.style.maxWidth = '100%';

    // user 消息上的附件先于文本气泡渲染
    if (msg.role === 'user' && msg.attachments && msg.attachments.length) {
      const attsEl = document.createElement('div');
      attsEl.className = 'msg-attachments';
      for (const att of msg.attachments) {
        const item = document.createElement('div');
        item.className = 'msg-att';
        if (att.mime.startsWith('image/')) {
          item.innerHTML = `<img src="${escapeAttr(att.object_url)}" alt="${escapeAttr(att.filename)}">`;
        } else {
          item.innerHTML = `
            <span class="msg-att-icon">📎</span>
            <span class="msg-att-name">${escapeText(att.filename)}</span>
          `;
        }
        attsEl.appendChild(item);
      }
      inner.appendChild(attsEl);
    }

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
    // user 消息没有正文（只有附件）时不渲空气泡
    if (msg.role !== 'user' || msg.content || !msg.attachments?.length) {
      inner.appendChild(bubble);
    }

    if (msg.role === 'user' && !msg.streaming) {
      // user 消息也加 Actions（copy / delete）
      inner.appendChild(this.buildMessageActions(msg));
    }

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
      if (!msg.streaming) {
        inner.appendChild(this.buildMessageActions(msg));
      }
    }

    wrap.appendChild(inner);
    return wrap;
  }

  private buildMessageActions(msg: WidgetMessage): HTMLDivElement {
    const tools = document.createElement('div');
    tools.className = 'msg-tools';

    // Copy（所有消息）
    const copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.title = '复制';
    copyBtn.innerHTML = copyIcon;
    copyBtn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(msg.content);
        const orig = copyBtn.innerHTML;
        copyBtn.innerHTML = checkIcon;
        copyBtn.classList.add('active');
        setTimeout(() => {
          copyBtn.innerHTML = orig;
          copyBtn.classList.remove('active');
        }, 1200);
      } catch {
        /* clipboard 不可用就静默 */
      }
    });
    tools.appendChild(copyBtn);

    // Regenerate（仅 assistant）
    if (msg.role === 'assistant') {
      const regen = document.createElement('button');
      regen.type = 'button';
      regen.title = '重新生成';
      regen.innerHTML = refreshIcon;
      regen.addEventListener('click', () => void this.regenerateMessage(msg.id));
      tools.appendChild(regen);
    }

    // 反馈（仅 assistant + 配置开 + 有 requestId）
    if (
      msg.role === 'assistant' &&
      this.behavior.show_feedback
    ) {
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
      if (!msg.requestId) {
        up.disabled = true;
        down.disabled = true;
      } else {
        const submit = (positive: boolean, btn: HTMLButtonElement) => {
          const other = positive ? down : up;
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
      }
      tools.appendChild(up);
      tools.appendChild(down);
    }

    // Delete（所有消息）
    const del = document.createElement('button');
    del.type = 'button';
    del.title = '删除';
    del.className = 'danger';
    del.innerHTML = trashIcon;
    del.addEventListener('click', () => this.deleteMessage(msg.id));
    tools.appendChild(del);

    return tools;
  }

  /** 删除消息（widget 本地态，不写后端） */
  private deleteMessage(id: string): void {
    const idx = this.messages.findIndex(m => m.id === id);
    if (idx < 0) return;
    this.messages.splice(idx, 1);
    const el = this.messagesEl.querySelector(`[data-mid="${id}"]`);
    el?.remove();
  }

  /** 重新生成 assistant 消息（基于前面那条 user） */
  private async regenerateMessage(id: string): Promise<void> {
    if (this.isSending) return;
    const idx = this.messages.findIndex(m => m.id === id);
    if (idx < 0 || this.messages[idx].role !== 'assistant') return;
    let userIdx = idx - 1;
    while (userIdx >= 0 && this.messages[userIdx].role !== 'user') userIdx--;
    if (userIdx < 0) return;
    const userInput = this.messages[userIdx].content;
    // 移除当前 assistant + 重发
    this.deleteMessage(id);
    await this.handleSend(userInput);
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
    // 至少要有文本或附件
    const ready = this.pendingAttachments.filter(a => a.object_url);
    if (!trimmed && !ready.length) return;
    if (this.pendingAttachments.length !== ready.length) {
      this.pushTransientNotice('还有附件在上传中，请等待完成', true);
      return;
    }
    if (!this.isOpen) this.toggle(true);

    this.isSending = true;
    this.textarea.value = '';
    this.textarea.style.height = 'auto';
    this.setComposerDisabled(true);

    // 清掉首屏的推荐问题面板（点击后已发，留着没意义）
    this.messagesEl.querySelector('.suggested-questions[data-role="suggested"]')?.remove();

    // 把附件挂在 user message 上；发送 / 落库后清空 pending
    const sendingAttachments = ready.slice();
    this.pushMessage({
      id: this.nextId(),
      role: 'user',
      content: trimmed,
      attachments: sendingAttachments.length ? sendingAttachments : undefined,
    });
    this.pendingAttachments = [];
    this.renderAttachmentChips();

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
        await this.runStream(pendingId, trimmed, sendingAttachments);
      } else {
        await this.runOneShot(pendingId, trimmed, sendingAttachments);
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

    // 回复完拉动态追问（受 behavior.show_followups 控制，失败静默）
    if (this.behavior.show_followups) {
      const last = this.messages.find(m => m.id === pendingId);
      if (last && !last.error && last.content) {
        this.fetchAndRenderFollowups(trimmed, last.content).catch(err =>
          console.warn('[ChameleonWidget] followups failed', err),
        );
      }
    }

    // 后台刷新侧栏（last_message_at / 新会话条目）—— 受 show_history_sidebar 控制
    if (this.config?.session_policy?.show_history_sidebar) {
      this.hydrateSessions().catch(err =>
        console.warn('[ChameleonWidget] sessions refresh failed', err),
      );
    }
  }

  private async fetchAndRenderFollowups(question: string, answer: string): Promise<void> {
    const token = await this.session.getToken();
    const list = await this.api.suggestFollowups(token, question, answer);
    if (!list.length) return;
    // 移除可能存在的旧 follow-ups（多轮快连发时只留最新）
    this.messagesEl.querySelector('.suggested-questions[data-role="followups"]')?.remove();
    const wrap = document.createElement('div');
    wrap.className = 'suggested-questions';
    wrap.dataset.role = 'followups';
    for (const q of list) {
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

  private async runOneShot(
    pendingId: string,
    input: string,
    attachments?: WidgetAttachment[],
  ): Promise<void> {
    const res = await this.session.invokeWithRetry(input, attachments);
    if (res.session_id && res.session_id !== this.currentSessionId) {
      this.currentSessionId = res.session_id;
      this.rememberSid(res.session_id);
    }
    this.updateMessage(pendingId, {
      content: res.answer,
      requestId: res.request_id ?? undefined,
      pending: false,
      streaming: false,
    });
  }

  private async runStream(
    pendingId: string,
    input: string,
    attachments?: WidgetAttachment[],
  ): Promise<void> {
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
          if (chunk.meta?.session_id && chunk.meta.session_id !== this.currentSessionId) {
            this.currentSessionId = chunk.meta.session_id;
            this.rememberSid(chunk.meta.session_id);
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
        attachments,
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

/** 相对时间：刚刚 / N 分钟前 / N 小时前 / N 天前 / yyyy-MM-dd */
function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return '';
  const diffSec = Math.max(0, (Date.now() - ts) / 1000);
  if (diffSec < 60) return '刚刚';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} 分钟前`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} 小时前`;
  if (diffSec < 86400 * 7) return `${Math.floor(diffSec / 86400)} 天前`;
  // 一周以上显示日期
  const d = new Date(ts);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

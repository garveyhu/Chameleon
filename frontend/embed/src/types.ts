/** 嵌入式 widget 共享类型 —— 与 admin 端 schema 1:1 对齐 */

export type ThemeMode = 'light' | 'dark' | 'auto';
export type BubblePosition = 'right-bottom' | 'left-bottom' | 'right-top' | 'left-top';
export type BubbleIcon = 'chat' | 'sparkles' | 'help-circle' | 'message-circle' | 'bot';
export type FontSize = 'sm' | 'md' | 'lg';
export type ShadowLevel = 'none' | 'sm' | 'md' | 'lg';

export interface UiConfig {
  theme_color?: string;
  /** 助手头像图片 URL；优先级高于 icon_emoji，渲在面板内消息气泡前 */
  icon_url?: string | null;
  icon_emoji?: string;
  title?: string;
  subtitle?: string;
  greeting?: string;
  placeholder?: string;
  bubble_position?: BubblePosition;
  bubble_color?: string;
  bubble_icon?: BubbleIcon;
  /** 浮窗图片（圆形 cover；非空时整个 bubble 用图片替代纯色 + 内置 icon） */
  bubble_image_url?: string | null;
  /** 浮窗大小（直径 px，默认 56） */
  bubble_size?: number;
  /** 浮窗背景透明：仅显 icon / 图片本体，无纯色圆背景 */
  bubble_transparent?: boolean;
  /** 浮窗旁招呼语 ——「hi, 让我帮助你～」 */
  bubble_tooltip_text?: string;
  bubble_tooltip_color?: string;
  bubble_tooltip_font_size?: number;
  bubble_tooltip_font_weight?: 'normal' | 'bold';
  /** 招呼语位置 —— left/right/top/bottom 直线；orbit 沿气泡顶部圆弧环绕 */
  bubble_tooltip_position?: 'left' | 'right' | 'top' | 'bottom' | 'orbit';
  /** 招呼语透明背景：去掉气泡白底 / 边框 / 阴影，只保留文字 */
  bubble_tooltip_transparent?: boolean;
  /** 面板打开后 tooltip 自动隐藏（默认 true） */
  bubble_tooltip_dismiss_on_open?: boolean;
  /** 面板打开后浮窗是否仍显示（默认 true） */
  bubble_persist_when_open?: boolean;
  /** 面板底部水印是否显示（默认 true） */
  show_powered_by?: boolean;
  /** 水印文字（默认 "powered by Chameleon"） */
  powered_by_text?: string;
  mode?: ThemeMode;
  border_radius?: number;
  font_size?: FontSize;
  panel_width?: number;
  panel_height?: number;
  header_bg?: string;
  /** 头部文字颜色；空 / 不传 = 自动反色 */
  header_text_color?: string;
  shadow?: ShadowLevel;
}

export interface BehaviorConfig {
  auto_open?: boolean;
  auto_open_delay_ms?: number;
  suggested_questions?: string[];
  show_feedback?: boolean;
  show_citations?: boolean;
  allow_file_upload?: boolean;
  streaming?: boolean;
  /** 回复后让 widget 调 /suggest-followups 拿 3 个动态追问气泡 */
  show_followups?: boolean;
  /** 单文件大小上限（MB）；默认 10 */
  max_file_size_mb?: number;
  /** 单条消息最多附件数；默认 5 */
  max_files_per_message?: number;
  /** 允许的附件 kind 白名单；默认 ['image','audio','document','data'] */
  allowed_file_kinds?: Array<'image' | 'audio' | 'document' | 'data'>;
}

/** /config 端点透出的 session_policy（密钥已剥） */
export interface PublicSessionPolicy {
  identification_mode?: 'anonymous_device' | 'external_user_id' | 'signed_jwt';
  show_history_sidebar?: boolean;
  auto_resume_last?: boolean;
  allow_user_manage?: boolean;
  max_history_days?: number;
}

export interface EmbedPublicConfig {
  embed_key: string;
  name: string;
  description: string | null;
  ui_config: UiConfig | null;
  behavior: BehaviorConfig | null;
  session_policy: PublicSessionPolicy | null;
}

export interface CreateSessionResponse {
  session_token: string;
  expires_in: number;
}

/** 历史会话条目（GET /sessions 返回） */
export interface EmbedSessionItem {
  session_id: string;
  title: string | null;
  last_message_at: string | null;
  created_at: string;
}

/** 显式开新对话（POST /sessions/new 返回） */
export interface CreateNewSessionResponse {
  session_token: string;
  session_id: string;
  expires_in: number;
}

/** GET /sessions/{sid}/messages 单条 */
export interface EmbedMessageItem {
  id: number | string;
  role: 'user' | 'assistant';
  content: string;
  seq?: number;
  created_at?: string;
  /** 后端可能透出的引用列表（assistant 行） */
  citations?: { title?: string; source?: string; snippet?: string }[];
  /** 用户消息的多模态 content blocks（attachments 历史回放用） */
  content_blocks?: { type: string; [k: string]: unknown }[];
  /** 本条消息所属调用的 trace_id —— widget 反馈按钮历史回放时按它落 score */
  request_id?: string | null;
  /** 用户对该消息的历史反馈：1 = 👍，-1 = 👎；后端按 scores 表 thumbs 反查 */
  feedback?: number | null;
}

export interface InvokeResponse {
  answer: string;
  session_id: string;
  request_id: string | null;
}

export interface ApiResult<T> {
  code: number;
  message: string;
  data: T;
  success: boolean;
}

export interface StreamChunk {
  meta?: { agent: string; session_id: string; request_id: string };
  delta?: string;
  citation?: {
    source?: string;
    title?: string;
    snippet?: string;
    [k: string]: unknown;
  };
  end?: boolean;
  usage?: { input_tokens?: number; output_tokens?: number; total_tokens?: number } | null;
  answer?: string;
  error?: { type: string; message: string };
}

/** widget 持有的附件元信息（已上传到 MinIO，拿到 object_url 后挂在消息上） */
export interface WidgetAttachment {
  object_url: string;
  filename: string;
  mime: string;
  size: number;
  /** Phase A 仅 image/audio 真正发送给后端；其他类型上传成功也只本地显示，提示用户切到长文档 */
  kind: 'image' | 'audio' | 'document' | 'data' | 'other';
  /** 后端 SessionFile 行 id（finalize 返回后填入；用于 polling status） */
  sessionFileId?: number | null;
  /**
   * 端侧 chip 状态机：
   *   uploading: 直传 MinIO 中
   *   parsing:   finalize 完成，后端异步解析（小文件全文 / 大文件 chunk）中
   *   indexing:  大文件正在切块 + embedding（仅大文件出现）
   *   ready:     可用于发送
   *   failed:    上传或解析失败
   * 未显式标注（undefined）= 图片 / 音频，finalize 后立即可用
   */
  status?: 'uploading' | 'parsing' | 'indexing' | 'ready' | 'failed';
  /** failed 时的错误说明 */
  error?: string | null;
}

export interface WidgetMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  /** assistant 的内联引用列表（show_citations=true 时渲染） */
  citations?: { title?: string; source?: string; snippet?: string }[];
  /** 用户消息上传的附件（用户气泡内渲缩略 / 卡片） */
  attachments?: WidgetAttachment[];
  /** 后端 SSE meta 透出的 request_id（= trace_id），用于反馈定位 */
  requestId?: string;
  /** 用户当前反馈：1 = 👍，-1 = 👎，null/undefined = 未点 */
  feedback?: 1 | -1 | null;
  pending?: boolean;
  streaming?: boolean;
  error?: boolean;
  /** 招呼语 / 系统提示等占位消息：不渲 actions（复制 / 重生成 / 反馈 / 删除） */
  isGreeting?: boolean;
}

export interface WidgetOptions {
  embedKey: string;
  apiBase: string;
  /** S12：终端用户外部标识（external_user_id 模式用） */
  externalUserId?: string;
  /** S12：接入方签名的 JWT（signed_jwt 模式用） */
  jwtToken?: string;
}

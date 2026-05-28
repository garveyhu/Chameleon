/** 嵌入式 widget 共享类型 —— 与 admin 端 schema 1:1 对齐 */

export type ThemeMode = 'light' | 'dark' | 'auto';
export type BubblePosition = 'right-bottom' | 'left-bottom' | 'right-top' | 'left-top';
export type BubbleIcon = 'chat' | 'sparkles' | 'help-circle' | 'message-circle' | 'bot';
export type FontSize = 'sm' | 'md' | 'lg';
export type ShadowLevel = 'none' | 'sm' | 'md' | 'lg';

export interface UiConfig {
  theme_color?: string;
  /** 自定义头像图片 URL；优先级高于 icon_emoji */
  icon_url?: string | null;
  icon_emoji?: string;
  title?: string;
  subtitle?: string;
  greeting?: string;
  placeholder?: string;
  bubble_position?: BubblePosition;
  bubble_color?: string;
  bubble_icon?: BubbleIcon;
  mode?: ThemeMode;
  border_radius?: number;
  font_size?: FontSize;
  panel_width?: number;
  panel_height?: number;
  header_bg?: string;
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

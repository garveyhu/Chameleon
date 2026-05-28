/** 嵌入式 widget 共享类型 —— 与 admin 端 schema 1:1 对齐 */

export type ThemeMode = 'light' | 'dark' | 'auto';
export type BubblePosition = 'right-bottom' | 'left-bottom' | 'right-top' | 'left-top';
export type BubbleIcon = 'chat' | 'sparkles' | 'help-circle' | 'message-circle' | 'bot';
export type FontSize = 'sm' | 'md' | 'lg';
export type ShadowLevel = 'none' | 'sm' | 'md' | 'lg';

export interface UiConfig {
  theme_color?: string;
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
}

export interface EmbedPublicConfig {
  embed_key: string;
  name: string;
  description: string | null;
  ui_config: UiConfig | null;
  behavior: BehaviorConfig | null;
}

export interface CreateSessionResponse {
  session_token: string;
  expires_in: number;
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

export interface WidgetMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  /** assistant 的内联引用列表（show_citations=true 时渲染） */
  citations?: { title?: string; source?: string; snippet?: string }[];
  /** 后端 SSE meta 透出的 request_id（= trace_id），用于反馈定位 */
  requestId?: string;
  /** 用户当前反馈：1 = 👍，-1 = 👎，null/undefined = 未点 */
  feedback?: 1 | -1 | null;
  pending?: boolean;
  streaming?: boolean;
  error?: boolean;
}

export interface WidgetOptions {
  embedKey: string;
  apiBase: string;
  /** S12：终端用户外部标识（external_user_id 模式用） */
  externalUserId?: string;
  /** S12：接入方签名的 JWT（signed_jwt 模式用） */
  jwtToken?: string;
}

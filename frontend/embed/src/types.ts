/** 嵌入式 widget 共享类型 */

export interface UiConfig {
  title?: string;
  subtitle?: string;
  primary_color?: string;
  position?: 'bottom-right' | 'bottom-left';
  width?: number;
  height?: number;
  bubble_icon?: string;
}

export interface BehaviorConfig {
  welcome_message?: string;
  placeholder?: string;
}

export interface EmbedPublicConfig {
  embed_key: string;
  name: string;
  description: string | null;
  ui_config: UiConfig | null;
  behavior: BehaviorConfig | null;
  welcome_message: string | null;
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

export interface WidgetMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  pending?: boolean;
  error?: boolean;
}

export interface WidgetOptions {
  embedKey: string;
  apiBase: string;
}

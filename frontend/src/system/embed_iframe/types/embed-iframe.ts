/** iframe 全屏对话相关类型 */

export interface IframeUiConfig {
  title?: string;
  subtitle?: string;
  primary_color?: string;
}

export interface IframeBehavior {
  welcome_message?: string;
  placeholder?: string;
  /** 建议问题（点击直接发送）—— 工作流 start 节点带过来 */
  suggested_questions?: string[];
}

export interface IframePublicConfig {
  embed_key: string;
  name: string;
  description: string | null;
  ui_config: IframeUiConfig | null;
  behavior: IframeBehavior | null;
  welcome_message: string | null;
}

export interface IframeCreateSessionResp {
  session_token: string;
  expires_in: number;
}

export interface IframeInvokeResp {
  answer: string;
  session_id: string;
  request_id: string | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  pending?: boolean;
  error?: boolean;
}

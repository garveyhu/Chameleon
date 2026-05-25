/** iframe 全屏对话相关类型 */

export interface IframeUiConfig {
  title?: string;
  subtitle?: string;
  primary_color?: string;
  /** 头像 emoji（留空用默认机器人图标） */
  icon_emoji?: string;
}

export interface IframeBehavior {
  welcome_message?: string;
  placeholder?: string;
  /** 建议问题（点击直接发送）—— 工作流 start 节点带过来 */
  suggested_questions?: string[];
  /** 在回答下方显示复制 / 朗读等操作（默认显示） */
  show_feedback?: boolean;
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

/** SSE 流式 chunk —— /v1/embed/{key}/invoke/stream 的 data 行（见后端 sse_events） */
export interface EmbedStreamChunk {
  meta?: { agent?: string; session_id?: string; request_id?: string };
  delta?: string;
  citation?: { source?: string; snippet?: string; score?: number | null };
  end?: boolean;
  usage?: unknown;
  answer?: string;
  error?: { type?: string; message?: string };
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  pending?: boolean;
  error?: boolean;
}

import type { EntityId } from '@/core/types/api';

export type ThemeMode = 'light' | 'dark' | 'auto';
export type BubblePosition = 'right-bottom' | 'left-bottom' | 'right-top' | 'left-top';
export type BubbleIcon = 'chat' | 'sparkles' | 'help-circle' | 'message-circle' | 'bot';
export type FontSize = 'sm' | 'md' | 'lg';
export type ShadowLevel = 'none' | 'sm' | 'md' | 'lg';

/** 嵌入式智能体外观 —— 16 项（Dify 全量对齐） */
export interface UiConfig {
  /** 主色 hex */
  theme_color: string;
  /** 头像 emoji（单字符 / 短组合） */
  icon_emoji: string;
  /** 面板顶部标题 */
  title: string;
  /** 副标题（标题下方一行小字） */
  subtitle: string;
  /** assistant 首条招呼语（支持换行） */
  greeting: string;
  /** 输入框 placeholder */
  placeholder: string;
  /** 浮窗气泡位置 */
  bubble_position: BubblePosition;
  /** 浮窗气泡背景色 hex（默认随主色） */
  bubble_color: string;
  /** 浮窗气泡图标 */
  bubble_icon: BubbleIcon;
  /** 主题模式 */
  mode: ThemeMode;
  /** 圆角 px */
  border_radius: number;
  /** 字体大小档位 */
  font_size: FontSize;
  /** 面板宽度 px */
  panel_width: number;
  /** 面板高度 px */
  panel_height: number;
  /** 头部背景色 hex（默认随主色） */
  header_bg: string;
  /** 阴影强度 */
  shadow: ShadowLevel;
}

/** 嵌入式智能体行为 —— 7 项（Dify 风） */
export interface Behavior {
  /** 页面加载后自动展开面板 */
  auto_open: boolean;
  /** auto_open 延迟（ms），0 = 立刻 */
  auto_open_delay_ms: number;
  /** 推荐问题列表（点击后直接发送） */
  suggested_questions: string[];
  /** 显示点赞 / 点踩 */
  show_feedback: boolean;
  /** 显示引用来源（来自 KB） */
  show_citations: boolean;
  /** 允许上传附件 */
  allow_file_upload: boolean;
  /** 流式输出（关闭则一次性返回） */
  streaming: boolean;
}

export const DEFAULT_UI_CONFIG: UiConfig = {
  theme_color: '#2563EB',
  icon_emoji: '🤖',
  title: 'AI 助手',
  subtitle: '在线为您服务',
  greeting: '你好！我是你的 AI 助手，有什么可以帮你的？',
  placeholder: '请输入你的问题…',
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

export const DEFAULT_BEHAVIOR: Behavior = {
  auto_open: false,
  auto_open_delay_ms: 0,
  suggested_questions: [],
  show_feedback: true,
  show_citations: true,
  allow_file_upload: false,
  streaming: true,
};

/** UI / behavior 字段补丁：兼容存量空值 / 部分字段 */
export const mergeUiConfig = (raw: Record<string, unknown> | null | undefined): UiConfig => ({
  ...DEFAULT_UI_CONFIG,
  ...(raw as Partial<UiConfig> | null | undefined),
});

export const mergeBehavior = (
  raw: Record<string, unknown> | null | undefined,
): Behavior => ({
  ...DEFAULT_BEHAVIOR,
  ...(raw as Partial<Behavior> | null | undefined),
});

export interface EmbedConfigItem {
  id: EntityId;
  embed_key: string;
  name: string;
  description: string | null;
  agent_id: EntityId;
  allowed_origins: string[] | null;
  ui_config: Record<string, unknown> | null;
  behavior: Record<string, unknown> | null;
  enabled: boolean;
  created_by_user_id: EntityId | null;
  created_at: string;
  updated_at: string;
}

export interface CreateEmbedConfigRequest {
  name: string;
  description?: string;
  agent_id: EntityId;
  allowed_origins?: string[];
  ui_config?: UiConfig;
  behavior?: Behavior;
}

export interface UpdateEmbedConfigRequest {
  name?: string;
  description?: string;
  allowed_origins?: string[];
  ui_config?: UiConfig;
  behavior?: Behavior;
  enabled?: boolean;
}

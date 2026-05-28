import type { EntityId } from '@/core/types/api';

export type ThemeMode = 'light' | 'dark' | 'auto';
export type BubblePosition = 'right-bottom' | 'left-bottom' | 'right-top' | 'left-top';
export type BubbleIcon = 'chat' | 'sparkles' | 'help-circle' | 'message-circle' | 'bot';
export type FontSize = 'sm' | 'md' | 'lg';
export type ShadowLevel = 'none' | 'sm' | 'md' | 'lg';

/** 嵌入式智能体外观 —— Dify 对齐 */
export interface UiConfig {
  /** 主色 hex */
  theme_color: string;
  /** 自定义头像图片 URL（MinIO presigned；优先级高于 icon_emoji） */
  icon_url: string | null;
  /** 头像 emoji（单字符 / 短组合）；icon_url 为空时使用 */
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
  /** 浮窗自定义图片 URL（非空时整个 bubble 用图片代替纯色 + 内置 icon） */
  bubble_image_url: string | null;
  /** 浮窗大小（直径 px，默认 56） */
  bubble_size: number;
  /** 浮窗背景透明：仅显 icon / 图片本体，无纯色圆形背景 */
  bubble_transparent: boolean;
  /** 浮窗旁招呼语（如 "hi, 让我帮助你～"，空字符串关闭） */
  bubble_tooltip_text: string;
  /** 招呼语文字颜色 hex */
  bubble_tooltip_color: string;
  /** 招呼语字号 px */
  bubble_tooltip_font_size: number;
  /** 招呼语粗细 */
  bubble_tooltip_font_weight: 'normal' | 'bold';
  /** 招呼语位置：left/right/top/bottom 直线；orbit 沿气泡顶部圆弧环绕（FastGPT 风） */
  bubble_tooltip_position: 'left' | 'right' | 'top' | 'bottom' | 'orbit';
  /** 招呼语透明背景（去掉背景 / 边框 / 阴影，只保留文字） */
  bubble_tooltip_transparent: boolean;
  /** 面板打开后自动隐藏招呼语（默认 true） */
  bubble_tooltip_dismiss_on_open: boolean;
  /** 打开会话后浮窗按钮是否仍可见（默认 true 保留；false 时面板打开后浮窗消失） */
  bubble_persist_when_open: boolean;
  /** 面板底部水印是否显示（默认 true） */
  show_powered_by: boolean;
  /** 水印文字（默认 "powered by Chameleon"，可改成 "Powered by Acme" 等） */
  powered_by_text: string;
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

export type FileKind = 'image' | 'audio' | 'document' | 'data';

/** 嵌入式智能体行为 —— Dify 风，含附件限制 3 项 */
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
  /** 回复后用 LLM 生成 3 个动态追问，渲在 assistant 气泡下方 */
  show_followups: boolean;
  /** 单文件大小上限（MB）；默认 10 */
  max_file_size_mb: number;
  /** 单条消息最多附件数；默认 5 */
  max_files_per_message: number;
  /** 允许的附件 kind 白名单 */
  allowed_file_kinds: FileKind[];
}

export const DEFAULT_UI_CONFIG: UiConfig = {
  theme_color: '#2563EB',
  icon_url: null,
  icon_emoji: '🤖',
  title: 'AI 助手',
  subtitle: '在线为您服务',
  greeting: '你好！我是你的 AI 助手，有什么可以帮你的？',
  placeholder: '请输入你的问题…',
  bubble_position: 'right-bottom',
  bubble_color: '#2563EB',
  bubble_icon: 'chat',
  bubble_image_url: null,
  bubble_size: 56,
  bubble_transparent: false,
  bubble_tooltip_text: '',
  bubble_tooltip_color: '#1f2937',
  bubble_tooltip_font_size: 13,
  bubble_tooltip_font_weight: 'normal',
  bubble_tooltip_position: 'left',
  bubble_tooltip_transparent: false,
  bubble_tooltip_dismiss_on_open: true,
  bubble_persist_when_open: true,
  show_powered_by: true,
  powered_by_text: 'powered by Chameleon',
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
  show_followups: false,
  max_file_size_mb: 10,
  max_files_per_message: 5,
  allowed_file_kinds: ['image', 'audio', 'document', 'data'],
};

/** 终端用户识别方式（S13 重构） */
export type IdentificationMode = 'anonymous_device' | 'external_user_id' | 'signed_jwt';

/** 嵌入式会话策略 —— 落 embed_configs.session_policy JSON */
export interface SessionPolicy {
  /** 终端用户识别方式 */
  identification_mode: IdentificationMode;
  /** signed_jwt 模式用的 HS256 共享密钥（加密存）；其他模式留空 */
  jwt_signing_secret_encrypted: string | null;
  /** widget 是否显示历史会话侧栏 */
  show_history_sidebar: boolean;
  /** 加载时是否自动续接 localStorage 里的上次会话 */
  auto_resume_last: boolean;
  /** 是否允许终端用户改名 / 删除自己的会话 */
  allow_user_manage: boolean;
  /** 历史会话列表的时间窗（天） */
  max_history_days: number;
}

export const DEFAULT_SESSION_POLICY: SessionPolicy = {
  identification_mode: 'anonymous_device',
  jwt_signing_secret_encrypted: null,
  show_history_sidebar: true,
  auto_resume_last: true,
  allow_user_manage: true,
  max_history_days: 90,
};

export const mergeSessionPolicy = (
  raw: Record<string, unknown> | null | undefined,
): SessionPolicy => ({
  ...DEFAULT_SESSION_POLICY,
  ...(raw as Partial<SessionPolicy> | null | undefined),
});

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
  /** S13：owner api_key（嵌入流量归属 / 复用 key 限流） */
  api_key_id: EntityId | null;
  allowed_origins: string[] | null;
  ui_config: Record<string, unknown> | null;
  behavior: Record<string, unknown> | null;
  /** S13：嵌入式会话策略（识别模式 / 侧栏 / 用户自管理） */
  session_policy: Record<string, unknown> | null;
  enabled: boolean;
  created_by_user_id: EntityId | null;
  created_at: string;
  updated_at: string;
}

export interface CreateEmbedConfigRequest {
  name: string;
  description?: string;
  agent_id: EntityId;
  api_key_id?: EntityId | null;
  allowed_origins?: string[];
  ui_config?: UiConfig;
  behavior?: Behavior;
  session_policy?: SessionPolicy;
}

export interface UpdateEmbedConfigRequest {
  name?: string;
  description?: string;
  api_key_id?: EntityId | null;
  allowed_origins?: string[];
  ui_config?: UiConfig;
  behavior?: Behavior;
  session_policy?: SessionPolicy;
  enabled?: boolean;
}

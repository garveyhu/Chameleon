/** MessageActions 公共契约
 *
 * 各消费方（playground / conversations / widget）把自己的消息映射成
 * ChatActionMessage 这一最小形态，并按需提供 handlers；组件据此决定渲染哪些 action。
 *
 * action 分两类：
 * - 内置（built-in）：copy / tts / export / share —— 组件自带默认实现，handler 可选（覆盖默认）
 * - 受控（handler-required）：edit / regenerate / delete / feedback / branch /
 *   translate / continueGen / pin —— 必须由消费方提供 handler 才渲染
 */

export type ChatActionRole = 'user' | 'assistant' | 'system' | 'tool';

export type MessageActionKey =
  | 'copy'
  | 'edit'
  | 'regenerate'
  | 'delete'
  | 'thumbsUp'
  | 'thumbsDown'
  | 'branching'
  | 'translate'
  | 'continueGen'
  | 'tts'
  | 'export'
  | 'share'
  | 'pin';

/** 消费方消息 → 组件最小形态 */
export interface ChatActionMessage {
  id: string;
  role: ChatActionRole;
  content: string;
  status?: 'streaming' | 'done' | 'failed';
  /** 1=👍 / -1=👎 / null=未点 */
  feedback?: 1 | -1 | null;
  pinned?: boolean;
}

export interface TranslateLanguage {
  /** 传给 onTranslate 的语言标识，如 'en' / 'zh' / 'ja' */
  code: string;
  label: string;
}

/**
 * 受控动作 handler 集合。
 * - 提供 handler = 该 action 可用（仍受 role/status 适用性约束）
 * - 内置动作（copy/tts/export/share）的 handler 为可选的「副作用钩子 / 覆盖」
 */
export interface MessageActionHandlers {
  /** copy 内置写剪贴板；此钩子在写入成功后触发（埋点 / toast 等） */
  onCopy?: () => void;
  onEdit?: () => void;
  onRegenerate?: () => void;
  onDelete?: () => void;
  /** 👍/👎 合一：组件计算 toggle 后回传最终值（再点同一个 → null） */
  onFeedback?: (value: 1 | -1 | null) => void;
  onBranch?: () => void;
  /** translate 受控：lang 为 translateLanguages 里选中的 code，未配语言列表时为 undefined */
  onTranslate?: (lang?: string) => void;
  onContinue?: () => void;
  /** 覆盖内置 Web Speech TTS；提供则组件不再自行朗读 */
  onTts?: () => void;
  /** 覆盖内置「下载单条 markdown」 */
  onExport?: () => void;
  /** 覆盖内置「复制分享片段」 */
  onShare?: () => void;
  /** pin 受控：回传切换后的目标态 */
  onPin?: (next: boolean) => void;
}

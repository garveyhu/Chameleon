/** 媒体/模型相关枚举集中维护 —— 前端各处复用，避免散落的死字符串。
 *  与后端 chameleon.integrations.mediagen.types 的 StrEnum 对齐。 */

export const MODEL_KINDS = [
  { value: 'chat', label: '对话 (chat)' },
  { value: 'embedding', label: '向量 (embedding)' },
  { value: 'rerank', label: '重排 (rerank)' },
  { value: 'image', label: '生图 (image)' },
] as const;
export type ModelKind = (typeof MODEL_KINDS)[number]['value'];

export const MEDIA_KINDS = ['image', 'video'] as const;
export type MediaKind = (typeof MEDIA_KINDS)[number];

/** 生图模型的生成后端（驱动） */
export const IMAGE_DRIVERS = [
  { value: 'comfyui', label: '本地 ComfyUI（工作流）' },
  { value: 'dashscope', label: 'DashScope 远程（千问 / 万相）' },
] as const;
export type ImageDriver = (typeof IMAGE_DRIVERS)[number]['value'];

/** DashScope 图片调用接口形态 */
export const IMAGE_API_STYLES = [
  { value: 'multimodal', label: '同步 multimodal（qwen-image-2.0 / 2.0-pro / max）' },
  { value: 'synthesis', label: '异步 text2image（qwen-image / plus、万相 wan）' },
] as const;
export type ImageApiStyle = (typeof IMAGE_API_STYLES)[number]['value'];

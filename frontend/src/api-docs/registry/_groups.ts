/** 端点分组定义 —— 控制左导航分组结构与顺序 */
import type { GroupMeta } from '@/api-docs/types/endpoint';

export const GROUPS: readonly GroupMeta[] = [
  { key: 'invoke', title: '应用调用', order: 10 },
  { key: 'sessions', title: '会话管理', order: 20 },
  { key: 'kb', title: '知识库', order: 30 },
  { key: 'embed', title: '嵌入式', order: 40 },
  { key: 'openai', title: 'OpenAI 兼容', order: 50 },
  { key: 'files', title: '文件', order: 60 },
];

/** 取分组 meta；未注册分组兜底成一个"其他"组 */
export function getGroup(key: string): GroupMeta {
  return GROUPS.find(g => g.key === key) ?? { key, title: key, order: 999 };
}

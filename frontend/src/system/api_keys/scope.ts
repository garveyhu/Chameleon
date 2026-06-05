/** API Key 作用域元数据 —— 标签 / 图标 / 配色，供卡片与分组头复用。
 *
 * 单独成文（非组件文件），避免 react-refresh/only-export-components。
 */

import { BookOpen, Bot, Globe } from 'lucide-react';
import type { ComponentType } from 'react';

import type { ApiKeyScopeType } from '@/system/api_keys/types/app';

export interface ScopeMeta {
  label: string;
  icon: ComponentType<{ className?: string }>;
  accent: string;
  chip: string;
}

export const SCOPE: Record<ApiKeyScopeType, ScopeMeta> = {
  global: {
    label: '通用',
    icon: Globe,
    accent: 'border-l-primary-400',
    chip: 'bg-primary-50 text-primary-700',
  },
  app: {
    label: '应用',
    icon: Bot,
    accent: 'border-l-emerald-400',
    chip: 'bg-emerald-50 text-emerald-700',
  },
  kb: {
    label: '知识库',
    icon: BookOpen,
    accent: 'border-l-amber-400',
    chip: 'bg-amber-50 text-amber-700',
  },
};

export const scopeMeta = (t: string): ScopeMeta =>
  SCOPE[(t as ApiKeyScopeType) in SCOPE ? (t as ApiKeyScopeType) : 'global'];

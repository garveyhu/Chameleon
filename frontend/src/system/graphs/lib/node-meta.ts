/** 节点类型元数据 —— 图标 / 配色 / 标签 / 输出字段
 *
 * 纯数据模块（无组件导出），供 canvas 节点、palette、inspector 面板共用，
 * 避免在组件文件里散落常量触发 react-refresh 规则。
 */
import {
  Bot,
  Braces,
  CircleDashed,
  Code2,
  Combine,
  CornerDownLeft,
  Database,
  Flag,
  GitBranch,
  Globe,
  type LucideIcon,
  PlayCircle,
  Repeat,
  Shuffle,
  Split,
  UserCheck,
  Users,
  Variable,
  Wrench,
} from 'lucide-react';

import type { GraphNodeType } from '@/system/graphs/types/graph';

export interface NodeTypeMeta {
  icon: LucideIcon;
  color: string;
  ring: string;
  bg: string;
  label: string;
}

export const TYPE_META: Record<GraphNodeType, NodeTypeMeta> = {
  start: {
    icon: PlayCircle,
    color: 'text-emerald-700',
    ring: 'ring-emerald-200',
    bg: 'bg-emerald-50',
    label: 'Start',
  },
  end: {
    icon: Flag,
    color: 'text-stone-700',
    ring: 'ring-stone-300',
    bg: 'bg-stone-50',
    label: 'End',
  },
  llm: {
    icon: Bot,
    color: 'text-violet-700',
    ring: 'ring-violet-200',
    bg: 'bg-violet-50',
    label: 'LLM',
  },
  kb: {
    icon: Database,
    color: 'text-emerald-700',
    ring: 'ring-emerald-200',
    bg: 'bg-emerald-50',
    label: 'KB',
  },
  tool: {
    icon: Wrench,
    color: 'text-orange-700',
    ring: 'ring-orange-200',
    bg: 'bg-orange-50',
    label: 'Tool',
  },
  if_else: {
    icon: GitBranch,
    color: 'text-amber-700',
    ring: 'ring-amber-200',
    bg: 'bg-amber-50',
    label: 'If/Else',
  },
  agent_debate: {
    icon: Users,
    color: 'text-fuchsia-700',
    ring: 'ring-fuchsia-200',
    bg: 'bg-fuchsia-50',
    label: 'Agent Debate',
  },
  iteration: {
    icon: Repeat,
    color: 'text-sky-700',
    ring: 'ring-sky-200',
    bg: 'bg-sky-50',
    label: 'Iteration',
  },
  parallel: {
    icon: Split,
    color: 'text-indigo-700',
    ring: 'ring-indigo-200',
    bg: 'bg-indigo-50',
    label: 'Parallel',
  },
  human_input: {
    icon: UserCheck,
    color: 'text-pink-700',
    ring: 'ring-pink-200',
    bg: 'bg-pink-50',
    label: 'Human Input',
  },
  http: {
    icon: Globe,
    color: 'text-cyan-700',
    ring: 'ring-cyan-200',
    bg: 'bg-cyan-50',
    label: 'HTTP',
  },
  aggregator: {
    icon: Combine,
    color: 'text-amber-800',
    ring: 'ring-amber-200',
    bg: 'bg-amber-50',
    label: 'Aggregator',
  },
  assign: {
    icon: Variable,
    color: 'text-rose-700',
    ring: 'ring-rose-200',
    bg: 'bg-rose-50',
    label: 'Assign',
  },
  classifier: {
    icon: Shuffle,
    color: 'text-lime-700',
    ring: 'ring-lime-200',
    bg: 'bg-lime-50',
    label: 'Classifier',
  },
  code: {
    icon: Code2,
    color: 'text-slate-700',
    ring: 'ring-slate-300',
    bg: 'bg-slate-50',
    label: 'Code',
  },
  template: {
    icon: Braces,
    color: 'text-teal-700',
    ring: 'ring-teal-200',
    bg: 'bg-teal-50',
    label: 'Template',
  },
  answer: {
    icon: CornerDownLeft,
    color: 'text-green-700',
    ring: 'ring-green-200',
    bg: 'bg-green-50',
    label: 'Answer',
  },
  noop: {
    icon: CircleDashed,
    color: 'text-stone-500',
    ring: 'ring-stone-200',
    bg: 'bg-white',
    label: 'Noop',
  },
};

/** 各节点类型的输出字段（变量选择器 + 输出变量区共用） */
export const NODE_OUTPUT_FIELDS: Partial<Record<GraphNodeType, string[]>> = {
  llm: ['answer'],
  kb: ['joined_context', 'hits', 'query'],
  http: ['status_code', 'body', 'headers'],
  template: ['text'],
  answer: ['answer'],
  if_else: ['branch', 'value'],
  agent_debate: ['answer'],
  classifier: ['category'],
  code: ['result'],
};

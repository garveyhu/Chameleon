/** 左侧 node palette —— 6 类节点拖到 canvas 创建 */

import {
  Bot,
  Braces,
  CircleDashed,
  Combine,
  CornerDownLeft,
  Database,
  Flag,
  GitBranch,
  Globe,
  PlayCircle,
  Repeat,
  Split,
  UserCheck,
  Users,
  Wrench,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { cn } from '@/core/lib/cn';
import type { GraphNodeType } from '@/system/graphs/types/graph';

interface PaletteItem {
  type: GraphNodeType;
  label: string;
  icon: LucideIcon;
  desc: string;
  color: string;
}

const ITEMS: PaletteItem[] = [
  {
    type: 'noop',
    label: 'Noop',
    icon: CircleDashed,
    desc: '占位 / 调试',
    color: 'text-stone-500',
  },
  {
    type: 'llm',
    label: 'LLM',
    icon: Bot,
    desc: '调模型生成',
    color: 'text-violet-600',
  },
  {
    type: 'kb',
    label: 'KB',
    icon: Database,
    desc: '检索知识库',
    color: 'text-emerald-600',
  },
  {
    type: 'tool',
    label: 'Tool',
    icon: Wrench,
    desc: '调工具（P18.2）',
    color: 'text-orange-600',
  },
  {
    type: 'if_else',
    label: 'If/Else',
    icon: GitBranch,
    desc: '条件分支',
    color: 'text-amber-600',
  },
  {
    type: 'agent_debate',
    label: 'Agent Debate',
    icon: Users,
    desc: '多 agent 辩论',
    color: 'text-fuchsia-600',
  },
  {
    type: 'iteration',
    label: 'Iteration',
    icon: Repeat,
    desc: '对列表逐元素跑子图',
    color: 'text-sky-600',
  },
  {
    type: 'parallel',
    label: 'Parallel',
    icon: Split,
    desc: '并发分支 fork-join',
    color: 'text-indigo-600',
  },
  {
    type: 'human_input',
    label: 'Human Input',
    icon: UserCheck,
    desc: '暂停等人工回填',
    color: 'text-pink-600',
  },
  {
    type: 'http',
    label: 'HTTP',
    icon: Globe,
    desc: '调外部 HTTP 接口',
    color: 'text-cyan-600',
  },
  {
    type: 'aggregator',
    label: 'Aggregator',
    icon: Combine,
    desc: '聚合多节点变量',
    color: 'text-amber-700',
  },
  {
    type: 'template',
    label: 'Template',
    icon: Braces,
    desc: '变量拼文本（{{#...#}}）',
    color: 'text-teal-600',
  },
  {
    type: 'answer',
    label: 'Answer',
    icon: CornerDownLeft,
    desc: '显式最终回答',
    color: 'text-green-600',
  },
  {
    type: 'end',
    label: 'End',
    icon: Flag,
    desc: '终态聚合',
    color: 'text-stone-700',
  },
];

interface Props {
  onAdd: (type: GraphNodeType) => void;
}

export const NodePalette = ({ onAdd }: Props) => {
  const onDragStart = (e: React.DragEvent, type: GraphNodeType) => {
    e.dataTransfer.setData('application/x-graph-node-type', type);
    e.dataTransfer.effectAllowed = 'copy';
  };

  return (
    <div className="flex h-full w-44 shrink-0 flex-col gap-1 border-r border-stone-200/70 bg-warm-2/40 p-2">
      <div className="mb-1 flex items-center gap-1 text-[10.5px] uppercase tracking-wider text-stone-500">
        <PlayCircle className="h-3 w-3" />
        节点
      </div>
      {ITEMS.map(it => (
        <button
          key={it.type}
          type="button"
          draggable
          onDragStart={e => onDragStart(e, it.type)}
          onClick={() => onAdd(it.type)}
          className={cn(
            'group flex items-start gap-2 rounded-md border border-stone-200 bg-white px-2 py-1.5 text-left text-[11.5px]',
            'transition hover:border-stone-300 hover:bg-stone-50',
            'active:cursor-grabbing',
          )}
          title={`拖到画布或点击添加 · ${it.desc}`}
        >
          <it.icon className={cn('mt-0.5 h-3.5 w-3.5 shrink-0', it.color)} />
          <div className="min-w-0 flex-1">
            <div className="font-medium text-stone-800">{it.label}</div>
            <div className="truncate text-[10px] text-stone-500">{it.desc}</div>
          </div>
        </button>
      ))}
      <div className="mt-2 rounded-md bg-stone-100/70 px-2 py-1.5 text-[10px] leading-snug text-stone-500">
        Tip：拖到画布；从节点边缘拽出连接线即可建边
      </div>
    </div>
  );
};

/** 左侧 node palette —— 分组 + 可滚动 + 可折叠；点击贴随光标放置，或拖到画布 */
import { useState } from 'react';

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
  PanelLeftClose,
  PanelLeftOpen,
  Repeat,
  Shuffle,
  Split,
  UserCheck,
  Users,
  Variable,
  Wrench,
} from 'lucide-react';

import { cn } from '@/core/lib/cn';
import { isNodeAllowedForKind } from '@/system/graphs/lib/node-meta';
import type { GraphKind, GraphNodeType } from '@/system/graphs/types/graph';

interface PaletteItem {
  type: GraphNodeType;
  label: string;
  icon: LucideIcon;
  desc: string;
  color: string;
  group: string;
}

const ITEMS: PaletteItem[] = [
  {
    type: 'llm',
    label: 'LLM',
    icon: Bot,
    desc: '调模型生成',
    color: 'text-violet-600',
    group: '生成',
  },
  {
    type: 'classifier',
    label: 'Classifier',
    icon: Shuffle,
    desc: 'LLM 意图分类',
    color: 'text-lime-600',
    group: '生成',
  },
  {
    type: 'agent_debate',
    label: 'Agent Debate',
    icon: Users,
    desc: '多 agent 辩论',
    color: 'text-fuchsia-600',
    group: '生成',
  },

  {
    type: 'kb',
    label: 'KB',
    icon: Database,
    desc: '检索知识库',
    color: 'text-emerald-600',
    group: '检索 & 工具',
  },
  {
    type: 'http',
    label: 'HTTP',
    icon: Globe,
    desc: '调外部 HTTP 接口',
    color: 'text-cyan-600',
    group: '检索 & 工具',
  },
  {
    type: 'code',
    label: 'Code',
    icon: Code2,
    desc: '沙箱跑代码',
    color: 'text-slate-600',
    group: '检索 & 工具',
  },
  {
    type: 'tool',
    label: 'Tool',
    icon: Wrench,
    desc: '调用外部工具',
    color: 'text-orange-600',
    group: '检索 & 工具',
  },

  {
    type: 'if_else',
    label: 'If/Else',
    icon: GitBranch,
    desc: '条件分支',
    color: 'text-amber-600',
    group: '逻辑',
  },
  {
    type: 'iteration',
    label: 'Iteration',
    icon: Repeat,
    desc: '对列表逐元素跑子图',
    color: 'text-sky-600',
    group: '逻辑',
  },
  {
    type: 'parallel',
    label: 'Parallel',
    icon: Split,
    desc: '并发分支 fork-join',
    color: 'text-indigo-600',
    group: '逻辑',
  },
  {
    type: 'human_input',
    label: 'Human Input',
    icon: UserCheck,
    desc: '暂停等人工回填',
    color: 'text-pink-600',
    group: '逻辑',
  },

  {
    type: 'template',
    label: 'Template',
    icon: Braces,
    desc: '变量拼文本',
    color: 'text-teal-600',
    group: '变量 & 输出',
  },
  {
    type: 'aggregator',
    label: 'Aggregator',
    icon: Combine,
    desc: '聚合多节点变量',
    color: 'text-amber-700',
    group: '变量 & 输出',
  },
  {
    type: 'assign',
    label: 'Assign',
    icon: Variable,
    desc: '写会话变量（跨轮）',
    color: 'text-rose-600',
    group: '变量 & 输出',
  },
  {
    type: 'answer',
    label: 'Answer',
    icon: CornerDownLeft,
    desc: '显式最终回答',
    color: 'text-green-600',
    group: '变量 & 输出',
  },
  {
    type: 'noop',
    label: 'Noop',
    icon: CircleDashed,
    desc: '占位 / 调试',
    color: 'text-stone-500',
    group: '变量 & 输出',
  },
  {
    type: 'end',
    label: 'End',
    icon: Flag,
    desc: '终态聚合',
    color: 'text-stone-700',
    group: '变量 & 输出',
  },
];

const GROUP_ORDER = ['生成', '检索 & 工具', '逻辑', '变量 & 输出'];

interface Props {
  /** 当前图类型；流程型会过滤掉对话型独占节点（如 Answer） */
  kind: GraphKind;
  /** 点击：开始放置（贴随光标，点画布落位）；组件不直接落位 */
  onAdd: (type: GraphNodeType) => void;
}

export const NodePalette = ({ kind, onAdd }: Props) => {
  const [collapsed, setCollapsed] = useState(true);

  const onDragStart = (e: React.DragEvent, type: GraphNodeType) => {
    e.dataTransfer.setData('application/x-graph-node-type', type);
    e.dataTransfer.effectAllowed = 'copy';
  };

  return (
    <div
      className={cn(
        'bg-warm-2/40 flex h-full shrink-0 flex-col border-r border-stone-200/70 transition-[width]',
        collapsed ? 'w-12' : 'w-44',
      )}
    >
      <div className="flex items-center justify-between px-3 py-2.5">
        {!collapsed && (
          <span className="text-[10.5px] tracking-wider text-stone-500 uppercase">节点</span>
        )}
        <button
          type="button"
          onClick={() => setCollapsed(c => !c)}
          title={collapsed ? '展开节点栏' : '收起节点栏'}
          className="rounded p-1 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4" />
          ) : (
            <PanelLeftClose className="h-4 w-4" />
          )}
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        {GROUP_ORDER.map(group => (
          <div key={group} className="mb-2.5">
            {!collapsed && (
              <div className="px-1 pb-1 text-[9.5px] font-medium tracking-wide text-stone-400 uppercase">
                {group}
              </div>
            )}
            <div className="space-y-1">
              {ITEMS.filter(it => it.group === group && isNodeAllowedForKind(it.type, kind)).map(
                it => (
                  <button
                    key={it.type}
                    type="button"
                    draggable
                    onDragStart={e => onDragStart(e, it.type)}
                    onClick={() => onAdd(it.type)}
                    title={`点击贴随光标放置，或拖到画布 · ${it.desc}`}
                    className={cn(
                      'group flex w-full items-center gap-2 rounded-md border border-stone-200 bg-white text-left transition hover:border-stone-300 hover:bg-stone-50 active:cursor-grabbing',
                      collapsed ? 'justify-center p-1.5' : 'px-2 py-1.5',
                    )}
                  >
                    <it.icon className={cn('h-3.5 w-3.5 shrink-0', it.color)} />
                    {!collapsed && (
                      <div className="min-w-0 flex-1">
                        <div className="text-[11.5px] font-medium text-stone-800">{it.label}</div>
                        <div className="truncate text-[10px] text-stone-500">{it.desc}</div>
                      </div>
                    )}
                  </button>
                ),
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

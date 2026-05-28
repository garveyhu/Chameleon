/** 左侧 node palette —— Dify 式：薄图标轨（仅「+」），点开浮动面板覆盖在画布上
 *
 * 不再常驻撑宽列：轨道固定 w-12，展开时面板 absolute 浮在画布上方，不挤画布。
 */
import { useEffect, useRef, useState } from 'react';

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
  Plus,
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
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // 点击面板外区域关闭
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const onDragStart = (e: React.DragEvent, type: GraphNodeType) => {
    e.dataTransfer.setData('application/x-graph-node-type', type);
    e.dataTransfer.effectAllowed = 'copy';
  };

  const pick = (type: GraphNodeType) => {
    onAdd(type);
    setOpen(false);
  };

  return (
    <div
      ref={rootRef}
      className="absolute top-3 left-3 z-20 flex flex-col gap-1 rounded-lg border border-stone-200/70 bg-white/95 p-1 shadow-md backdrop-blur"
    >
      {/* 「+」开关 */}
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        title={open ? '收起节点面板' : '添加节点'}
        className={cn(
          'flex h-6 w-6 items-center justify-center rounded-md transition',
          open
            ? 'bg-blue-50 text-blue-600'
            : 'text-stone-500 hover:bg-stone-100 hover:text-stone-800',
        )}
      >
        <Plus className="h-3.5 w-3.5" />
      </button>

      {/* 浮动节点面板：absolute 叠在画布上方，不挤画布宽度 */}
      {open && (
        <div className="absolute top-0 left-[calc(100%+8px)] z-30 flex max-h-[calc(100vh-2rem)] w-56 flex-col rounded-xl border border-stone-200/80 bg-white shadow-lg">
          <div className="flex items-center justify-between px-3 pt-3 pb-1.5">
            <span className="text-[10.5px] tracking-wider text-stone-500 uppercase">节点</span>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            {GROUP_ORDER.map(group => (
              <div key={group} className="mb-2.5">
                <div className="px-1 pb-1 text-[9.5px] font-medium tracking-wide text-stone-400 uppercase">
                  {group}
                </div>
                <div className="space-y-1">
                  {ITEMS.filter(
                    it => it.group === group && isNodeAllowedForKind(it.type, kind),
                  ).map(it => (
                    <button
                      key={it.type}
                      type="button"
                      draggable
                      onDragStart={e => onDragStart(e, it.type)}
                      onClick={() => pick(it.type)}
                      title={`点击贴随光标放置，或拖到画布 · ${it.desc}`}
                      className="group flex w-full items-center gap-2 rounded-md border border-stone-200 bg-white px-2 py-1.5 text-left transition hover:border-stone-300 hover:bg-stone-50 active:cursor-grabbing"
                    >
                      <it.icon className={cn('h-3.5 w-3.5 shrink-0', it.color)} />
                      <div className="min-w-0 flex-1">
                        <div className="text-[11.5px] font-medium text-stone-800">{it.label}</div>
                        <div className="truncate text-[10px] text-stone-500">{it.desc}</div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

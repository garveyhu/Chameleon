/** 通用 graph node 渲染组件 —— 接 React Flow 的 NodeProps */

import { Handle, Position } from '@xyflow/react';
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
  PlayCircle,
  Repeat,
  Shuffle,
  Split,
  UserCheck,
  Users,
  Variable,
  Wrench,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { cn } from '@/core/lib/cn';
import type { GraphNodeType, NodeRunItem } from '@/system/graphs/types/graph';

const TYPE_META: Record<
  GraphNodeType,
  { icon: LucideIcon; color: string; ring: string; bg: string; label: string }
> = {
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

const STATUS_COLOR: Record<NodeRunItem['status'], string> = {
  pending: 'border-stone-300',
  running: 'border-blue-400 animate-pulse',
  success: 'border-emerald-400',
  failed: 'border-rose-500',
  skipped: 'border-stone-200',
};

export interface GraphNodeData {
  // React Flow Node<T> 要求 data 满足 Record<string, unknown>
  [key: string]: unknown;
  label: string;
  nodeType: GraphNodeType;
  selected?: boolean;
  runStatus?: NodeRunItem['status'];
  errorMessage?: string;
}

interface Props {
  data: GraphNodeData;
}

export const GraphNode = ({ data }: Props) => {
  const meta = TYPE_META[data.nodeType] ?? TYPE_META.noop;
  const statusCls = data.runStatus ? STATUS_COLOR[data.runStatus] : '';
  const isIfElse = data.nodeType === 'if_else';
  const hasInput = data.nodeType !== 'start';
  const hasOutput = data.nodeType !== 'end';

  return (
    <div
      className={cn(
        'min-w-[140px] rounded-md border-2 px-2.5 py-1.5 text-[11.5px] shadow-sm transition',
        meta.bg,
        statusCls || 'border-stone-300',
        data.selected && 'ring-2 ring-offset-1',
        data.selected && meta.ring,
      )}
    >
      {hasInput && (
        <Handle
          type="target"
          position={Position.Left}
          className="!h-2 !w-2 !border-stone-400 !bg-white"
        />
      )}

      <div className="flex items-center gap-1.5">
        <meta.icon className={cn('h-3.5 w-3.5 shrink-0', meta.color)} />
        <span className={cn('font-mono text-[10px] font-medium', meta.color)}>
          {meta.label}
        </span>
        <span className="ml-auto truncate text-stone-800">{data.label}</span>
      </div>

      {data.errorMessage && (
        <div
          className="mt-1 truncate text-[10px] text-rose-600"
          title={data.errorMessage}
        >
          ✗ {data.errorMessage}
        </div>
      )}

      {/* if_else 两个 source handle：true / false */}
      {isIfElse ? (
        <>
          <Handle
            id="true"
            type="source"
            position={Position.Right}
            style={{ top: '35%' }}
            className="!h-2 !w-2 !border-emerald-400 !bg-emerald-100"
          />
          <Handle
            id="false"
            type="source"
            position={Position.Right}
            style={{ top: '70%' }}
            className="!h-2 !w-2 !border-rose-400 !bg-rose-100"
          />
          <div className="mt-1 flex justify-between text-[9px] text-stone-500">
            <span />
            <div className="flex flex-col gap-0.5 text-right">
              <span className="text-emerald-600">→ true</span>
              <span className="text-rose-500">→ false</span>
            </div>
          </div>
        </>
      ) : hasOutput ? (
        <Handle
          type="source"
          position={Position.Right}
          className="!h-2 !w-2 !border-stone-400 !bg-white"
        />
      ) : null}
    </div>
  );
};

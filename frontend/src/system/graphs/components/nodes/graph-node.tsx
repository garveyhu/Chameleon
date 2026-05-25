/** 通用 graph node 渲染组件 —— 接 React Flow 的 NodeProps */
import { Handle, Position } from '@xyflow/react';

import { cn } from '@/core/lib/cn';
import { TYPE_META } from '@/system/graphs/lib/node-meta';
import type { GraphNodeType, NodeRunItem } from '@/system/graphs/types/graph';

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
        <span className={cn('font-mono text-[10px] font-medium', meta.color)}>{meta.label}</span>
        <span className="ml-auto truncate text-stone-800">{data.label}</span>
      </div>

      {data.errorMessage && (
        <div className="mt-1 truncate text-[10px] text-rose-600" title={data.errorMessage}>
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

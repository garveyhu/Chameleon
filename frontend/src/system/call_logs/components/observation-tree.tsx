/** 嵌套 Observation 树视图 —— 按 observation_type 渲染 icon + 缩进 + duration 条
 *
 * 数据：TraceTreeNode 嵌套结构（后端 /call-logs/{rid}/tree 返）
 * 视觉：
 *   - 每个节点一行：[icon] type   name(agent_key)   ─────━━━ duration(ms)
 *   - 子节点缩进 16px，含细灰色 vertical guide 线
 *   - duration 条按"占父节点总时长比例"画
 *   - 失败节点用红字 + 错误 message tooltip
 */

import {
  AlertCircle,
  Bot,
  CircleDashed,
  Cpu,
  Database,
  Layers,
  ShieldCheck,
  Sparkles,
  Wrench,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { Badge } from '@/core/components/ui/badge';
import { cn } from '@/core/lib/cn';
import { formatNumber } from '@/core/lib/format';
import type {
  ObservationType,
  TraceTreeNode,
} from '@/system/call_logs/types/call-log';

const TYPE_ICON: Record<ObservationType, LucideIcon> = {
  trace: Layers,
  span: CircleDashed,
  generation: Sparkles,
  agent: Bot,
  tool: Wrench,
  retriever: Database,
  evaluator: ShieldCheck,
  embedding: Cpu,
  guardrail: ShieldCheck,
};

const TYPE_COLOR: Record<ObservationType, string> = {
  trace: 'text-stone-700',
  span: 'text-stone-500',
  generation: 'text-violet-600',
  agent: 'text-blue-600',
  tool: 'text-orange-600',
  retriever: 'text-emerald-600',
  evaluator: 'text-amber-600',
  embedding: 'text-cyan-600',
  guardrail: 'text-rose-600',
};

interface ObservationTreeProps {
  root: TraceTreeNode;
  /** 选中节点的 request_id；点击节点回调 */
  selectedId?: string;
  onSelect?: (node: TraceTreeNode) => void;
}

export const ObservationTree: React.FC<ObservationTreeProps> = ({
  root,
  selectedId,
  onSelect,
}) => {
  const total = root.duration_ms || 1;
  return (
    <div className="space-y-0.5 font-mono text-[11.5px]">
      <TreeRow
        node={root}
        depth={0}
        totalDuration={total}
        selectedId={selectedId}
        onSelect={onSelect}
      />
    </div>
  );
};

interface TreeRowProps {
  node: TraceTreeNode;
  depth: number;
  totalDuration: number;
  selectedId?: string;
  onSelect?: (node: TraceTreeNode) => void;
}

const TreeRow: React.FC<TreeRowProps> = ({
  node,
  depth,
  totalDuration,
  selectedId,
  onSelect,
}) => {
  const otype = (node.observation_type as ObservationType) || 'generation';
  const Icon = TYPE_ICON[otype] ?? CircleDashed;
  const colorCls = TYPE_COLOR[otype] ?? 'text-stone-500';

  const widthPct = Math.max(2, Math.min(100, (node.duration_ms / totalDuration) * 100));
  const isSelected = selectedId === node.request_id;

  return (
    <>
      <button
        type="button"
        className={cn(
          'group relative flex w-full items-center gap-2 rounded px-1 py-1 text-left transition',
          'hover:bg-stone-100/70',
          isSelected && 'bg-blue-50/80 ring-1 ring-blue-200',
        )}
        style={{ paddingLeft: depth * 14 + 4 }}
        onClick={() => onSelect?.(node)}
      >
        {/* depth guide lines */}
        {depth > 0 ? (
          <span
            className="pointer-events-none absolute top-0 bottom-0 border-l border-stone-200/80"
            style={{ left: (depth - 1) * 14 + 10 }}
          />
        ) : null}

        <Icon className={cn('h-3.5 w-3.5 shrink-0', colorCls)} />
        <span className={cn('w-16 shrink-0 font-medium', colorCls)}>{otype}</span>

        <span className="min-w-0 flex-1 truncate text-stone-800">
          {node.agent_key}
          {node.success ? null : (
            <span className="ml-1.5 inline-flex items-center gap-0.5 text-rose-500">
              <AlertCircle className="h-3 w-3" />
              {node.error_message ? node.error_message.slice(0, 40) : '失败'}
            </span>
          )}
        </span>

        {/* tokens（generation 才有） */}
        {node.total_tokens ? (
          <Badge variant="outline" className="font-mono text-[10px]">
            {formatNumber(node.total_tokens)} tok
          </Badge>
        ) : null}

        {/* duration 条 + 数字 */}
        <div className="flex w-32 shrink-0 items-center gap-1.5">
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-stone-100">
            <div
              className={cn(
                'h-full transition-all',
                node.success ? 'bg-blue-400' : 'bg-rose-400',
              )}
              style={{ width: `${widthPct}%` }}
            />
          </div>
          <span className="tnum w-12 text-right text-[10.5px] text-stone-500">
            {node.duration_ms}ms
          </span>
        </div>
      </button>

      {node.children.length > 0
        ? node.children.map(child => (
            <TreeRow
              key={String(child.id)}
              node={child}
              depth={depth + 1}
              totalDuration={totalDuration}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          ))
        : null}
    </>
  );
};


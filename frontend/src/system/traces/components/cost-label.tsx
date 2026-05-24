/** Gantt bar 上叠加的成本 / token 标注
 *
 * 有 cost_usd（Agent C C2 聚合接入后）显成本，否则降级显 total_tokens。
 */

import { cn } from '@/core/lib/cn';
import { formatCost, formatTokens } from '@/core/lib/format';
import type { TraceTreeNode } from '@/system/call_logs/types/call-log';

interface Props {
  node: TraceTreeNode;
  className?: string;
}

export const CostLabel = ({ node, className }: Props) => {
  const hasCost = node.cost_usd != null;
  const text = hasCost
    ? formatCost(node.cost_usd)
    : node.total_tokens != null
      ? `${formatTokens(node.total_tokens)} tok`
      : null;
  if (!text) return null;
  return (
    <span
      className={cn(
        'pointer-events-none font-mono text-[10px] tabular-nums',
        hasCost ? 'text-emerald-700' : 'text-stone-400',
        className,
      )}
    >
      {text}
    </span>
  );
};

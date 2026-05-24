/** 单节点运行结果渲染 —— inspector「运行结果」区 + run dialog 进度行共用 */

import { JsonViewer } from '@/core/components/common/json-viewer';
import { StatusBadge } from '@/core/components/ui/status-badge';
import { formatDurationMs } from '@/core/lib/format';
import type { NodeRunView } from '@/system/graphs/types/graph';

const STATUS_TONE = {
  running: 'running',
  success: 'success',
  failed: 'error',
  skipped: 'neutral',
  pending: 'neutral',
} as const;

const STATUS_LABEL: Record<NodeRunView['status'], string> = {
  running: '执行中',
  success: '成功',
  failed: '失败',
  skipped: '跳过',
  pending: '待执行',
};

export const NodeRunStatusBadge = ({ status }: { status: NodeRunView['status'] }) => (
  <StatusBadge tone={STATUS_TONE[status]} pulse={status === 'running'}>
    {STATUS_LABEL[status]}
  </StatusBadge>
);

interface Props {
  run: NodeRunView;
  /** 折叠 input（默认展开 output、折叠 input） */
  compact?: boolean;
}

export const NodeRunResult = ({ run }: Props) => {
  const hasOutput = run.output !== undefined && run.output !== null;
  return (
    <div className="flex flex-col gap-2 text-[11.5px]">
      <div className="flex items-center gap-2">
        <NodeRunStatusBadge status={run.status} />
        {run.duration_ms != null && (
          <span className="tnum text-[10.5px] text-stone-500">
            {formatDurationMs(run.duration_ms)}
          </span>
        )}
      </div>

      {run.error && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-2 py-1.5 text-rose-700">
          <div className="font-mono text-[10px] uppercase tracking-wide text-rose-400">
            {run.error.type}
          </div>
          <div className="break-words">{run.error.message}</div>
        </div>
      )}

      {run.streamText && (
        <div>
          <div className="mb-1 text-[10.5px] uppercase tracking-wide text-stone-400">
            流式输出
          </div>
          <div className="max-h-40 overflow-auto whitespace-pre-wrap rounded-md border border-stone-200 bg-white px-2 py-1.5 font-mono text-[11px] leading-snug text-stone-700">
            {run.streamText}
          </div>
        </div>
      )}

      {hasOutput && (
        <div>
          <div className="mb-1 text-[10.5px] uppercase tracking-wide text-stone-400">
            output
          </div>
          <JsonViewer
            value={run.output}
            searchable={false}
            defaultExpanded
            maxHeight="240px"
          />
        </div>
      )}

      {run.input !== undefined && run.input !== null && (
        <details>
          <summary className="cursor-pointer text-[10.5px] uppercase tracking-wide text-stone-400 hover:text-stone-600">
            input
          </summary>
          <div className="mt-1">
            <JsonViewer
              value={run.input}
              searchable={false}
              defaultExpanded={false}
              maxHeight="200px"
            />
          </div>
        </details>
      )}
    </div>
  );
};

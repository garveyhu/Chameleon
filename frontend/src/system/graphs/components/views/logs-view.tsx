/** 日志视图 —— 该 graph 的历史运行（graph_runs）分页列表 + 点击查看详情
 *
 * 列表走 graphApi.listRuns（分页）；点行打开 Sheet 看运行详情（含逐节点 node_runs、
 * 入参 / 输出 / 错误）。数据全部来自真实 graph_runs / graph_node_runs。
 */
import { useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronRight, PlayCircle, ScrollText } from 'lucide-react';

import { DataTable, TablePagination, TableToolbar } from '@/core/components/table';
import type { DataTableColumn } from '@/core/components/table';
import { DateTimeRangePicker } from '@/core/components/ui/datetime-range-picker';
import type { DateTimeRange } from '@/core/components/ui/datetime-range-picker';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import { StatusBadge } from '@/core/components/ui/status-badge';
import type { StatusTone } from '@/core/components/ui/status-badge';
import { Tooltip } from '@/core/components/ui/tooltip';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { graphApi } from '@/system/graphs/services/graph';
import type { GraphRunDetail, GraphRunItem, NodeRunItem } from '@/system/graphs/types/graph';

interface Props {
  graphId: EntityId;
  graphName: string;
  /** 受控：当前展开详情的 run（编辑器从历史 RUNS 面板跳转时设置） */
  openRunId: EntityId | null;
  onOpenRun: (id: EntityId | null) => void;
}

const STATUS_TONE: Record<string, StatusTone> = {
  success: 'success',
  failed: 'error',
  running: 'running',
  paused: 'warning',
  pending: 'neutral',
  cancelled: 'neutral',
};

const STATUS_LABEL: Record<string, string> = {
  success: '成功',
  failed: '失败',
  running: '运行中',
  paused: '暂停',
  pending: '等待',
  cancelled: '已取消',
};

// 'all' = 未筛选（TableToolbar 用 allLabel 显示「全部状态」），故选项不含 all
const STATUS_OPTIONS = [
  { value: 'success', label: '成功' },
  { value: 'failed', label: '失败' },
  { value: 'running', label: '运行中' },
  { value: 'paused', label: '暂停' },
  { value: 'cancelled', label: '已取消' },
];

export const LogsView = ({ graphId, openRunId, onOpenRun }: Props) => {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [status, setStatus] = useState('all');
  const [sessionInput, setSessionInput] = useState('');
  const [sessionQ, setSessionQ] = useState('');
  const [range, setRange] = useState<DateTimeRange>({});

  const q = useQuery({
    queryKey: ['graph-runs', graphId, page, pageSize, status, sessionQ, range.start, range.end],
    queryFn: () =>
      graphApi.listRuns(graphId, {
        page,
        page_size: pageSize,
        status: status === 'all' ? undefined : status,
        session_id: sessionQ || undefined,
        since: range.start,
        until: range.end,
      }),
  });

  const columns: DataTableColumn<GraphRunItem>[] = [
    {
      key: 'status',
      header: '状态',
      width: 96,
      render: r => (
        <StatusBadge tone={STATUS_TONE[r.status] ?? 'neutral'}>
          {STATUS_LABEL[r.status] ?? r.status}
        </StatusBadge>
      ),
    },
    {
      key: 'nodes',
      header: '节点数',
      width: 80,
      render: r => <span className="text-[12px] text-stone-600">{r.node_count ?? '—'}</span>,
    },
    {
      key: 'duration',
      header: '耗时',
      width: 96,
      render: r => (
        <span className="font-mono text-[11.5px] text-stone-600">
          {r.duration_ms != null ? `${r.duration_ms}ms` : '—'}
        </span>
      ),
    },
    {
      key: 'session',
      header: '会话',
      width: 140,
      render: r =>
        r.session_id ? (
          <Tooltip content={r.session_id}>
            <span className="block truncate font-mono text-[10.5px] text-stone-500">
              {r.session_id}
            </span>
          </Tooltip>
        ) : (
          <span className="text-[11px] text-stone-300">—</span>
        ),
    },
    {
      key: 'request_id',
      header: '请求 ID',
      render: r => (
        <Tooltip content={r.request_id}>
          <span className="block truncate font-mono text-[10.5px] text-stone-400">
            {r.request_id}
          </span>
        </Tooltip>
      ),
    },
    {
      key: 'created_at',
      header: '时间',
      width: 168,
      render: r => (
        <span className="font-mono text-[11px] text-stone-500">{formatDateTime(r.created_at)}</span>
      ),
    },
    {
      key: 'arrow',
      header: '',
      width: 36,
      render: () => <ChevronRight className="h-3.5 w-3.5 text-stone-300" />,
    },
  ];

  return (
    <div className="h-full overflow-y-auto">
      <div className="px-10 py-8">
        {/* 标题 + 筛选同一行（waveflow 范式）：状态 / 会话搜索（带按钮）/ 时间范围 */}
        <TableToolbar
          title={
            <span className="flex items-center gap-2">
              <ScrollText className="h-4 w-4 text-stone-500" />
              <span className="text-[15px] font-semibold text-stone-900">运行日志</span>
              <span className="text-[12px] font-normal text-stone-400">
                共 {q.data?.total ?? 0} 次
              </span>
            </span>
          }
          search={{
            value: sessionInput,
            onChange: setSessionInput,
            onSubmit: v => {
              setSessionQ(v.trim());
              setPage(1);
            },
            placeholder: '会话 ID',
            width: 200,
          }}
          filters={[
            {
              value: status,
              onChange: v => {
                setStatus(v);
                setPage(1);
              },
              placeholder: '状态',
              allLabel: '全部状态',
              options: STATUS_OPTIONS,
            },
          ]}
          extra={
            <DateTimeRangePicker
              value={range}
              onChange={r => {
                setRange(r);
                setPage(1);
              }}
              placeholder="时间范围"
            />
          }
        />

        <DataTable
          columns={columns}
          rows={q.data?.items ?? []}
          rowKey={r => String(r.id)}
          loading={q.isLoading}
          onRowClick={r => onOpenRun(r.id)}
          emptyText="还没有运行记录；发布为智能体后对话 / 调用即可在此查看"
        />
        {(q.data?.total ?? 0) > 0 && (
          <div className="mt-3">
            <TablePagination
              page={page}
              pageSize={pageSize}
              total={q.data?.total ?? 0}
              onPageChange={setPage}
              onPageSizeChange={s => {
                setPageSize(s);
                setPage(1);
              }}
            />
          </div>
        )}
      </div>

      <RunDetailSheet runId={openRunId} onClose={() => onOpenRun(null)} />
    </div>
  );
};

// ── 运行详情抽屉 ───────────────────────────────────────────

const RunDetailSheet = ({ runId, onClose }: { runId: EntityId | null; onClose: () => void }) => {
  const q = useQuery({
    queryKey: ['graph-run', runId],
    queryFn: () => graphApi.getRun(runId as EntityId),
    enabled: runId != null,
  });
  const run = q.data;

  return (
    <Sheet open={runId != null} onOpenChange={o => !o && onClose()}>
      <SheetContent side="right" width="w-[560px]" className="flex flex-col p-0">
        <SheetHeader className="border-b border-stone-200/70 px-5 py-3.5">
          <SheetTitle className="flex items-center gap-2 text-[14px]">
            运行详情
            {run && (
              <StatusBadge tone={STATUS_TONE[run.status] ?? 'neutral'}>
                {STATUS_LABEL[run.status] ?? run.status}
              </StatusBadge>
            )}
          </SheetTitle>
        </SheetHeader>
        <SheetBody className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {q.isLoading && <div className="text-[12px] text-stone-400">加载中…</div>}
          {run && (
            <>
              <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[12px]">
                <Meta label="耗时" value={run.duration_ms != null ? `${run.duration_ms}ms` : '—'} />
                <Meta label="节点数" value={String(run.node_count ?? run.node_runs.length)} />
                <Meta label="开始" value={run.started_at ? formatDateTime(run.started_at) : '—'} />
                <Meta
                  label="结束"
                  value={run.finished_at ? formatDateTime(run.finished_at) : '—'}
                />
                <Meta label="会话 session" value={run.session_id || '—'} mono span2 />
                <Meta label="request_id" value={run.request_id} mono span2 />
              </div>

              {run.error && (
                <Field label="错误">
                  <pre className="overflow-x-auto rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 font-mono text-[11px] whitespace-pre-wrap text-rose-700">
                    {run.error.type}: {run.error.message}
                  </pre>
                </Field>
              )}

              {run.status === 'paused' && <ResumeSection run={run} />}

              <Field label="输入">
                <Json value={run.input} />
              </Field>
              <Field label="输出">
                <Json value={run.output} />
              </Field>

              <Field label={`节点执行（${run.node_runs.length}）`}>
                {run.node_runs.length ? (
                  <div className="space-y-2">
                    {run.node_runs.map((n, i) => (
                      <NodeRunCard key={`${n.node_id}-${i}`} n={n} />
                    ))}
                  </div>
                ) : (
                  <div className="rounded-md border border-dashed border-stone-200 px-3 py-2 text-[11.5px] text-stone-400">
                    无逐节点记录
                  </div>
                )}
              </Field>
            </>
          )}
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
};

/** paused run 的人工回填区：拉对应 pending 断点（prompt / 期望结构），回填 JSON 续跑 */
const ResumeSection = ({ run }: { run: GraphRunDetail }) => {
  const qc = useQueryClient();
  const [valueText, setValueText] = useState('{}');

  const pendingQ = useQuery({
    queryKey: ['graph-pending-inputs'],
    queryFn: () => graphApi.listPendingInputs('pending'),
  });
  // 雪花 id 可能 string/number 混合，一律 String() 归一比较
  const pending = (pendingQ.data ?? []).find(
    p => String(p.graph_run_id) === String(run.id),
  );

  const resumeMut = useMutation({
    mutationFn: (value: Record<string, unknown>) => graphApi.resumeRun(run.id, value),
    onSuccess: r => {
      toast.success(r.status === 'paused' ? '已回填，流程再次暂停于下一断点' : '已回填续跑');
      qc.invalidateQueries({ queryKey: ['graph-run', run.id] });
      qc.invalidateQueries({ queryKey: ['graph-runs'] });
      qc.invalidateQueries({ queryKey: ['graph-pending-inputs'] });
    },
    onError: e => toast.error(`回填失败：${(e as Error).message}`),
  });

  const submit = () => {
    let value: Record<string, unknown>;
    try {
      const parsed: unknown = JSON.parse(valueText || '{}');
      if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
        toast.error('回填值须是 JSON 对象（作为 human_input 节点的输出注入）');
        return;
      }
      value = parsed as Record<string, unknown>;
    } catch {
      toast.error('JSON 解析失败，请检查格式');
      return;
    }
    resumeMut.mutate(value);
  };

  return (
    <Field label="人工回填续跑">
      <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2.5">
        {pending?.prompt && (
          <div className="text-[12px] text-amber-900">{pending.prompt}</div>
        )}
        <div className="flex items-center gap-2 text-[10.5px] text-amber-700/80">
          {pending && (
            <span className="rounded bg-amber-100 px-1.5 py-0.5 font-mono">
              断点节点 {pending.node_id}
            </span>
          )}
          {pending?.timeout_at && <span>超时 {formatDateTime(pending.timeout_at)}</span>}
          {!pending && !pendingQ.isLoading && (
            <span>未找到断点记录（已超时清理或旧版本运行），无法回填</span>
          )}
        </div>
        {pending?.input_schema && (
          <details className="text-[10.5px] text-amber-700/80">
            <summary className="cursor-pointer select-none">期望结构（input_schema）</summary>
            <pre className="mt-1 max-h-32 overflow-auto rounded bg-stone-900 px-2 py-1.5 font-mono text-[10.5px] text-stone-100">
              {JSON.stringify(pending.input_schema, null, 2)}
            </pre>
          </details>
        )}
        <textarea
          value={valueText}
          onChange={e => setValueText(e.target.value)}
          rows={3}
          spellCheck={false}
          placeholder='{"approved": true}'
          className="w-full rounded-md border border-amber-200 bg-white px-2.5 py-1.5 font-mono text-[11.5px] text-stone-800 focus:border-amber-400 focus:outline-none"
        />
        <button
          type="button"
          onClick={submit}
          // 无断点行的 paused run（旧版本/已清理）回填必失败——直接禁用防误导
          disabled={resumeMut.isPending || (!pending && !pendingQ.isLoading)}
          className="inline-flex items-center gap-1.5 rounded-md bg-amber-600 px-3 py-1.5 text-[12px] font-medium text-white transition hover:bg-amber-700 disabled:opacity-50"
        >
          <PlayCircle className="h-3.5 w-3.5" />
          {resumeMut.isPending ? '回填中…' : '回填并续跑'}
        </button>
      </div>
    </Field>
  );
};

const NodeRunCard = ({ n }: { n: NodeRunItem }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-stone-200 bg-white">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        <span className="rounded bg-stone-100 px-1.5 py-0.5 font-mono text-[10px] text-stone-600">
          {n.node_type}
        </span>
        <span className="truncate font-mono text-[11.5px] text-stone-700">{n.node_id}</span>
        <StatusBadge tone={STATUS_TONE[n.status] ?? 'neutral'}>
          {STATUS_LABEL[n.status] ?? n.status}
        </StatusBadge>
        <span className="ml-auto font-mono text-[10.5px] text-stone-400">{n.duration_ms}ms</span>
        <ChevronRight
          className={cn('h-3.5 w-3.5 text-stone-300 transition', open && 'rotate-90')}
        />
      </button>
      {open && (
        <div className="space-y-2 border-t border-stone-100 px-3 py-2">
          {n.error && (
            <pre className="overflow-x-auto rounded border border-rose-200 bg-rose-50 px-2 py-1.5 font-mono text-[10.5px] whitespace-pre-wrap text-rose-700">
              {n.error.type}: {n.error.message}
            </pre>
          )}
          <div>
            <div className="mb-1 text-[10.5px] text-stone-400">输出</div>
            <Json value={n.output} small />
          </div>
        </div>
      )}
    </div>
  );
};

// ── 小组件 ────────────────────────────────────────────────

const Meta = ({
  label,
  value,
  mono,
  span2,
}: {
  label: string;
  value: string;
  mono?: boolean;
  span2?: boolean;
}) => (
  <div className={cn(span2 && 'col-span-2')}>
    <div className="text-[10.5px] text-stone-400">{label}</div>
    <div className={cn('truncate text-stone-700', mono && 'font-mono text-[11px]')}>{value}</div>
  </div>
);

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div>
    <div className="mb-1.5 text-[11.5px] font-medium text-stone-600">{label}</div>
    {children}
  </div>
);

const Json = ({ value, small }: { value: unknown; small?: boolean }) => {
  if (value == null || (typeof value === 'object' && Object.keys(value).length === 0)) {
    return <div className="text-[11px] text-stone-400">—</div>;
  }
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  return (
    <pre
      className={cn(
        'max-h-64 overflow-auto rounded-lg bg-stone-900 px-3 py-2 font-mono leading-relaxed text-stone-100',
        small ? 'text-[10.5px]' : 'text-[11px]',
      )}
    >
      {text}
    </pre>
  );
};

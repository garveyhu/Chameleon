/** 数据集详情页 —— 样本 Items / 运行 Runs 两 tab；点 run 开运行详情抽屉。 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  Download,
  FileSpreadsheet,
  GitCompare,
  Pencil,
  Upload,
} from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { DataTable, type DataTableColumn } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { JsonCell } from '@/core/components/ui/json-cell';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import { formatScore, scoreColor } from '@/core/lib/score';
import type { EntityId } from '@/core/types/api';
import { BulkImportModal } from '@/system/datasets/components/bulk-import-modal';
import { DatasetItemEditorDrawer } from '@/system/datasets/components/dataset-item-editor-drawer';
import { RunCompareMatrix } from '@/system/datasets/components/run-compare-matrix';
import { RunDetailDrawer } from '@/system/datasets/components/run-detail-drawer';
import { SampleFromLogsModal } from '@/system/datasets/components/sample-from-logs-modal';
import { datasetApi } from '@/system/datasets/services/dataset';
import { exportItems } from '@/system/datasets/utils/dataset-xlsx';
import type {
  DatasetItemRow,
  DatasetRunRow,
} from '@/system/datasets/types/dataset';

type Tab = 'items' | 'runs';

const STATUS_LABEL: Record<string, string> = {
  pending: '等待',
  running: '运行中',
  success: '成功',
  failed: '失败',
  cancelled: '已取消',
};
const statusBg = (s: string): string =>
  s === 'success'
    ? 'bg-emerald-50 text-emerald-700'
    : s === 'failed'
      ? 'bg-rose-50 text-rose-700'
      : 'bg-stone-50 text-stone-600';

const runScore = (r: DatasetRunRow): number | null => {
  const s = r.summary as Record<string, unknown> | null;
  if (!s) return null;
  const v = s.mean_score ?? s.mean ?? s.avg_score;
  return typeof v === 'number' ? v : null;
};
const runOkTotal = (r: DatasetRunRow): string => {
  const s = r.summary as Record<string, unknown> | null;
  if (!s) return '—';
  const ok = s.ok ?? s.passed;
  const total = s.total ?? s.count;
  return typeof ok === 'number' && typeof total === 'number'
    ? `${ok}/${total}`
    : '—';
};

export const DatasetDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  // ⚠️ dsId 保留 string —— snowflake 64-bit 超 MAX_SAFE_INTEGER，Number() 会精度丢失
  const dsId = id ?? '';
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>('items');
  const [runId, setRunId] = useState<EntityId | null>(null);
  const [selRunIds, setSelRunIds] = useState<EntityId[]>([]);
  const [runsView, setRunsView] = useState<'list' | 'matrix'>('list');
  const [sampleOpen, setSampleOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [editItem, setEditItem] = useState<DatasetItemRow | null>(null);

  const toggleRun = (rid: EntityId) =>
    setSelRunIds(p => (p.includes(rid) ? p.filter(x => x !== rid) : [...p, rid]));

  const dsQ = useQuery({
    queryKey: ['datasets', dsId],
    queryFn: () => datasetApi.get(dsId),
    enabled: !!dsId,
  });
  const itemsQ = useQuery({
    queryKey: ['datasets', dsId, 'items'],
    queryFn: () => datasetApi.listItems(dsId, 200),
    enabled: !!dsId,
  });
  const runsQ = useQuery({
    queryKey: ['datasets', dsId, 'runs'],
    queryFn: () => datasetApi.listRuns(dsId),
    enabled: !!dsId && tab === 'runs',
  });

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: ['datasets', dsId] });
    qc.invalidateQueries({ queryKey: ['datasets', dsId, 'items'] });
  };

  if (!dsId) {
    return <div className="p-6 text-sm text-stone-500">非法的数据集编号</div>;
  }

  const itemCols: DataTableColumn<DatasetItemRow>[] = [
    {
      key: 'source',
      header: '来源',
      width: 96,
      render: it => {
        const isLog = !!it.source_call_log_id;
        return (
          <span
            className={cn(
              'rounded px-1.5 py-0.5 text-[10.5px]',
              isLog
                ? 'bg-emerald-50 text-emerald-700'
                : 'bg-indigo-50 text-indigo-700',
            )}
          >
            {isLog ? '日志采样' : '手工导入'}
          </span>
        );
      },
    },
    {
      key: 'input',
      header: '输入',
      render: it => <JsonCell value={it.input_payload} />,
    },
    {
      key: 'expected',
      header: '预期输出',
      render: it => <JsonCell value={it.expected_output} />,
    },
    {
      key: 'sampled',
      header: '采样时间',
      align: 'right',
      width: 160,
      render: it => (
        <span className="text-[11px] text-stone-500">
          {formatDateTime(String(sampledAt(it)))}
        </span>
      ),
    },
    {
      key: 'annotate',
      header: '',
      align: 'right',
      width: 48,
      render: it => (
        <button
          type="button"
          onClick={e => {
            e.stopPropagation();
            setEditItem(it);
          }}
          title="编辑样本"
          className="rounded p-1 text-stone-400 hover:bg-stone-100 hover:text-stone-700"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
      ),
    },
  ];

  const runCols: DataTableColumn<DatasetRunRow>[] = [
    {
      key: 'sel',
      header: '',
      width: 36,
      render: r => (
        <input
          type="checkbox"
          checked={selRunIds.includes(r.id)}
          onClick={e => e.stopPropagation()}
          onChange={() => toggleRun(r.id)}
          className="h-3.5 w-3.5 accent-stone-700"
        />
      ),
    },
    {
      key: 'name',
      header: '运行',
      render: r => <span className="text-stone-800">{r.name}</span>,
    },
    {
      key: 'status',
      header: '状态',
      width: 84,
      render: r => (
        <Badge
          variant="outline"
          className={cn('text-[10.5px]', statusBg(r.status))}
        >
          {STATUS_LABEL[r.status] ?? r.status}
        </Badge>
      ),
    },
    {
      key: 'judge',
      header: '评分器',
      width: 120,
      render: r => <span className="text-stone-600">{r.judge}</span>,
    },
    {
      key: 'score',
      header: '平均分',
      align: 'right',
      width: 84,
      render: r => {
        const s = runScore(r);
        return (
          <span className={cn('tnum', scoreColor(s))}>
            {s != null ? formatScore(s) : '—'}
          </span>
        );
      },
    },
    {
      key: 'ok',
      header: '通过',
      align: 'right',
      width: 72,
      render: r => (
        <span className="tnum text-stone-500">{runOkTotal(r)}</span>
      ),
    },
    {
      key: 'created_at',
      header: '时间',
      align: 'right',
      width: 150,
      render: r => (
        <span className="text-[11px] text-stone-500">
          {formatDateTime(r.created_at)}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <header className="flex items-center gap-3">
        <Link
          to="/datasets"
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12.5px] text-stone-500 hover:bg-stone-100 hover:text-stone-800"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> 数据集
        </Link>
        <span className="text-stone-300">/</span>
        {dsQ.isLoading ? (
          <span className="text-[12.5px] text-stone-400">加载中…</span>
        ) : dsQ.data ? (
          <div className="flex flex-1 items-baseline gap-2">
            <span className="text-[15px] font-medium text-stone-900">
              {dsQ.data.name}
            </span>
            <span className="text-[11.5px] text-stone-500">
              · {dsQ.data.item_count} 样本
            </span>
            <span className="ml-auto" />
            <Button
              size="sm"
              variant="ghost"
              disabled={!itemsQ.data?.length}
              onClick={() =>
                void exportItems(
                  dsQ.data?.name ?? '评测样本',
                  itemsQ.data ?? [],
                  'xlsx',
                )
              }
            >
              <FileSpreadsheet className="mr-1 h-3.5 w-3.5" /> 导出
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setImportOpen(true)}
            >
              <Upload className="mr-1 h-3.5 w-3.5" /> 手工导入
            </Button>
            <Button size="sm" onClick={() => setSampleOpen(true)}>
              <Download className="mr-1 h-3.5 w-3.5" /> 从日志采样
            </Button>
          </div>
        ) : (
          <span className="text-[12.5px] text-stone-400">未找到</span>
        )}
      </header>

      <div className="flex items-center justify-between">
        <div className="inline-flex gap-1 rounded-lg border border-stone-200 bg-white p-0.5">
          {(
            [
              ['items', '样本'],
              ['runs', '运行'],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              type="button"
              onClick={() => setTab(k)}
              className={cn(
                'rounded-md px-3 py-1 text-[13px] transition',
                tab === k
                  ? 'bg-stone-800 text-white'
                  : 'text-stone-600 hover:bg-stone-100',
              )}
            >
              {label}
            </button>
          ))}
        </div>
        {tab === 'runs' &&
          (runsView === 'matrix' ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setRunsView('list')}
            >
              ← 返回运行列表
            </Button>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-[11.5px] text-stone-400">
                {selRunIds.length > 0
                  ? `已选 ${selRunIds.length} 个`
                  : '勾选 2+ 个运行可对比'}
              </span>
              <Button
                size="sm"
                variant="secondary"
                disabled={selRunIds.length < 2}
                onClick={() => setRunsView('matrix')}
              >
                <GitCompare className="mr-1 h-3.5 w-3.5" /> 对比所选
              </Button>
              {selRunIds.length > 0 && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setSelRunIds([])}
                >
                  清空
                </Button>
              )}
            </div>
          ))}
      </div>

      {tab === 'items' ? (
        <DataTable
          columns={itemCols}
          rows={itemsQ.data ?? []}
          rowKey="id"
          loading={itemsQ.isLoading}
          emptyText="暂无样本，点右上「从日志采样」或「手工导入」开始"
          minWidth={680}
        />
      ) : runsView === 'matrix' ? (
        <RunCompareMatrix runIds={selRunIds} />
      ) : (
        <DataTable
          columns={runCols}
          rows={runsQ.data ?? []}
          rowKey="id"
          leftBar={r => statusBar(r.status)}
          loading={runsQ.isLoading}
          onRowClick={r => setRunId(r.id)}
          emptyText="还没有运行；在 Playground 或评测任务里跑一次会出现在这里"
          minWidth={620}
        />
      )}

      <RunDetailDrawer
        key={runId ?? '∅'}
        runId={runId}
        onClose={() => setRunId(null)}
      />

      {editItem && (
        <DatasetItemEditorDrawer
          item={editItem}
          onClose={() => setEditItem(null)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ['datasets', dsId, 'items'] });
            setEditItem(null);
          }}
        />
      )}

      {sampleOpen && (
        <SampleFromLogsModal
          datasetId={dsId}
          onClose={() => setSampleOpen(false)}
          onDone={() => {
            refreshAll();
            setSampleOpen(false);
          }}
        />
      )}
      {importOpen && (
        <BulkImportModal
          datasetId={dsId}
          onClose={() => setImportOpen(false)}
          onDone={() => {
            refreshAll();
            setImportOpen(false);
          }}
        />
      )}
    </div>
  );
};

const statusBar = (s: string): string =>
  s === 'success'
    ? 'bg-emerald-400'
    : s === 'failed'
      ? 'bg-rose-400'
      : 'bg-stone-300';

function sampledAt(item: DatasetItemRow): unknown {
  const meta = item.meta as Record<string, unknown> | null;
  return meta?.sampled_at ?? meta?.imported_at ?? item.created_at;
}

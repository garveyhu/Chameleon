/** 数据集详情页 —— 样本 Items / 运行 Runs 两 tab；点 run 跳运行详情整页。 */
import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  Download,
  FileSpreadsheet,
  GitCompare,
  Pencil,
  Play,
  Sparkles,
  Trash2,
  Upload,
} from 'lucide-react';

import { DataTable, type DataTableColumn, TablePagination } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { JsonCell } from '@/core/components/ui/json-cell';
import { confirm } from '@/core/lib/confirm';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import { formatScore, scoreColor } from '@/core/lib/score';
import type { EntityId } from '@/core/types/api';
import { AiGenerateModal } from '@/system/datasets/components/ai-generate-modal';
import { BulkImportModal } from '@/system/datasets/components/bulk-import-modal';
import { DatasetItemEditorDrawer } from '@/system/datasets/components/dataset-item-editor-drawer';
import { DatasetItemsSelectionBar } from '@/system/datasets/components/dataset-items-selection-bar';
import { DatasetSpreadsheet } from '@/system/datasets/components/dataset-spreadsheet';
import { NewEvaluationWizard } from '@/system/datasets/components/new-evaluation-wizard';
import { RunStatsOverview } from '@/system/datasets/components/run-stats-overview';
import { SampleFromLogsModal } from '@/system/datasets/components/sample-from-logs-modal';
import { useDatasetItemMutations } from '@/system/datasets/hooks/useDatasetItemMutations';
import { datasetApi } from '@/system/datasets/services/dataset';
import type { DatasetItemRow, DatasetRunRow } from '@/system/datasets/types/dataset';
import { exportItems } from '@/system/datasets/utils/dataset-xlsx';

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
  return typeof ok === 'number' && typeof total === 'number' ? `${ok}/${total}` : '—';
};

export const DatasetDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  // ⚠️ dsId 保留 string —— snowflake 64-bit 超 MAX_SAFE_INTEGER，Number() 会精度丢失
  const dsId = id ?? '';
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('items');
  const [selRunIds, setSelRunIds] = useState<EntityId[]>([]);
  const [itemsView, setItemsView] = useState<'table' | 'sheet'>('table');
  const [sampleOpen, setSampleOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [aiGenOpen, setAiGenOpen] = useState(false);
  const [evalOpen, setEvalOpen] = useState(false);
  const [editItem, setEditItem] = useState<DatasetItemRow | null>(null);
  const [itemPage, setItemPage] = useState(1);
  const [itemPageSize, setItemPageSize] = useState(50);
  const [selItemIds, setSelItemIds] = useState<EntityId[]>([]);
  const [runSort, setRunSort] = useState<{
    key: string;
    order: 'asc' | 'desc';
  }>({ key: 'created_at', order: 'desc' });

  const toggleRun = (rid: EntityId) =>
    setSelRunIds(p => (p.includes(rid) ? p.filter(x => x !== rid) : [...p, rid]));

  const { batchRemove } = useDatasetItemMutations(dsId);

  const dsQ = useQuery({
    queryKey: ['datasets', dsId],
    queryFn: () => datasetApi.get(dsId),
    enabled: !!dsId,
  });
  const itemsQ = useQuery({
    queryKey: ['datasets', dsId, 'items', itemPage, itemPageSize],
    queryFn: () => datasetApi.listItems(dsId, { page: itemPage, page_size: itemPageSize }),
    enabled: !!dsId,
    placeholderData: keepPreviousData,
  });
  const runsQ = useQuery({
    queryKey: ['datasets', dsId, 'runs'],
    queryFn: () => datasetApi.listRuns(dsId),
    enabled: !!dsId && tab === 'runs',
  });
  const judgesQ = useQuery({
    queryKey: ['datasets', 'judges'],
    queryFn: () => datasetApi.listJudges(),
    staleTime: 60_000,
  });

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: ['datasets', dsId] });
    qc.invalidateQueries({ queryKey: ['datasets', dsId, 'items'] });
  };

  const items = useMemo(() => itemsQ.data?.items ?? [], [itemsQ.data]);
  const itemsTotal = itemsQ.data?.total ?? 0;
  const pageIds = useMemo(() => items.map(it => it.id), [items]);
  const selectedSet = useMemo(() => new Set(selItemIds), [selItemIds]);
  const allPageSelected = pageIds.length > 0 && pageIds.every(id => selectedSet.has(id));

  const toggleItem = (id: EntityId) =>
    setSelItemIds(p => (p.includes(id) ? p.filter(x => x !== id) : [...p, id]));
  const toggleAllPage = () =>
    setSelItemIds(p =>
      allPageSelected
        ? p.filter(id => !pageIds.includes(id))
        : [...new Set([...p, ...pageIds])],
    );

  const handleDeleteOne = async (it: DatasetItemRow) => {
    const ok = await confirm({
      title: '删除样本',
      description: '删除后不可恢复，确认删除这条样本？',
      confirmText: '删除',
      danger: true,
    });
    if (!ok) return;
    batchRemove.mutate([it.id], {
      onSuccess: () => setSelItemIds(p => p.filter(id => id !== it.id)),
    });
  };

  const handleBatchDelete = async () => {
    if (selItemIds.length === 0) return;
    const ok = await confirm({
      title: `删除已选 ${selItemIds.length} 条样本`,
      description: '删除后不可恢复，确认批量删除？',
      confirmText: '删除',
      danger: true,
    });
    if (!ok) return;
    batchRemove.mutate([...selItemIds], { onSuccess: () => setSelItemIds([]) });
  };

  if (!dsId) {
    return <div className="p-6 text-sm text-stone-500">非法的数据集编号</div>;
  }

  const itemCols: DataTableColumn<DatasetItemRow>[] = [
    {
      key: 'sel',
      header: (
        <input
          type="checkbox"
          aria-label="全选本页"
          checked={allPageSelected}
          onChange={toggleAllPage}
          className="h-3.5 w-3.5 accent-stone-700"
        />
      ),
      width: 36,
      render: it => (
        <input
          type="checkbox"
          aria-label="选择该样本"
          checked={selectedSet.has(it.id)}
          onClick={e => e.stopPropagation()}
          onChange={() => toggleItem(it.id)}
          className="h-3.5 w-3.5 accent-stone-700"
        />
      ),
    },
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
              isLog ? 'bg-emerald-50 text-emerald-700' : 'bg-indigo-50 text-indigo-700',
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
        <span className="text-[11px] text-stone-500">{formatDateTime(String(sampledAt(it)))}</span>
      ),
    },
    {
      key: 'annotate',
      header: '',
      align: 'right',
      width: 76,
      render: it => (
        <span className="inline-flex items-center gap-0.5">
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
          <button
            type="button"
            onClick={e => {
              e.stopPropagation();
              void handleDeleteOne(it);
            }}
            title="删除样本"
            className="rounded p-1 text-stone-300 hover:bg-rose-50 hover:text-rose-600"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </span>
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
      render: r => (
        <span className="flex items-center gap-1.5">
          <span className="text-stone-800">{r.name}</span>
          {r.parent_run_id != null && (
            <Badge
              variant="outline"
              className="bg-violet-50 px-1 py-0 text-[9.5px] text-violet-700"
            >
              优化产物
            </Badge>
          )}
          {r.has_optimization && (
            <span title="已生成优化 Prompt">
              <Sparkles className="h-3 w-3 text-violet-400" />
            </span>
          )}
        </span>
      ),
    },
    {
      key: 'status',
      header: '状态',
      width: 84,
      sortable: true,
      render: r => (
        <Badge variant="outline" className={cn('text-[10.5px]', statusBg(r.status))}>
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
      sortable: true,
      render: r => {
        const s = runScore(r);
        return (
          <span className={cn('tnum', scoreColor(s))}>{s != null ? formatScore(s) : '—'}</span>
        );
      },
    },
    {
      key: 'ok',
      header: '通过',
      align: 'right',
      width: 72,
      render: r => <span className="tnum text-stone-500">{runOkTotal(r)}</span>,
    },
    {
      key: 'created_at',
      header: '时间',
      align: 'right',
      width: 150,
      sortable: true,
      render: r => (
        <span className="text-[11px] text-stone-500">{formatDateTime(r.created_at)}</span>
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
            <span className="text-[15px] font-medium text-stone-900">{dsQ.data.name}</span>
            <span className="text-[11.5px] text-stone-500">· {dsQ.data.item_count} 样本</span>
            <span className="ml-auto" />
            <Button
              size="sm"
              variant="ghost"
              disabled={items.length === 0}
              onClick={() => void exportItems(dsQ.data?.name ?? '评测样本', items, 'xlsx')}
            >
              <FileSpreadsheet className="mr-1 h-3.5 w-3.5" /> 导出
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setImportOpen(true)}>
              <Upload className="mr-1 h-3.5 w-3.5" /> 手工导入
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setAiGenOpen(true)}>
              <Sparkles className="mr-1 h-3.5 w-3.5" /> AI 扩样
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setSampleOpen(true)}>
              <Download className="mr-1 h-3.5 w-3.5" /> 从日志采样
            </Button>
            <Button size="sm" onClick={() => setEvalOpen(true)}>
              <Play className="mr-1 h-3.5 w-3.5" /> 新建评估
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
                tab === k ? 'bg-stone-800 text-white' : 'text-stone-600 hover:bg-stone-100',
              )}
            >
              {label}
            </button>
          ))}
        </div>
        {tab === 'items' && (
          <div className="inline-flex gap-1 rounded-lg border border-stone-200 bg-white p-0.5">
            {(
              [
                ['table', '表格'],
                ['sheet', '电子表格'],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                type="button"
                onClick={() => setItemsView(k)}
                className={cn(
                  'rounded-md px-3 py-1 text-[12.5px] transition',
                  itemsView === k ? 'bg-stone-800 text-white' : 'text-stone-600 hover:bg-stone-100',
                )}
              >
                {label}
              </button>
            ))}
          </div>
        )}
        {tab === 'runs' && (
          <div className="flex items-center gap-2">
            <span className="text-[11.5px] text-stone-400">
              {selRunIds.length > 0 ? `已选 ${selRunIds.length} 个` : '勾选 2+ 个运行可对比'}
            </span>
            <Button
              size="sm"
              variant="secondary"
              disabled={selRunIds.length < 2}
              onClick={() =>
                navigate(
                  `/datasets/${dsId}/runs/compare?ids=${selRunIds.map(String).join(',')}`,
                )
              }
            >
              <GitCompare className="mr-1 h-3.5 w-3.5" /> 对比所选
            </Button>
            {selRunIds.length > 0 && (
              <Button size="sm" variant="ghost" onClick={() => setSelRunIds([])}>
                清空
              </Button>
            )}
            <Button size="sm" onClick={() => setEvalOpen(true)}>
              <Play className="mr-1 h-3.5 w-3.5" /> 新建评估
            </Button>
          </div>
        )}
      </div>

      {tab === 'items' ? (
        <div className="space-y-3">
          <DatasetItemsSelectionBar
            selectedCount={selItemIds.length}
            deleting={batchRemove.isPending}
            onClear={() => setSelItemIds([])}
            onDelete={() => void handleBatchDelete()}
          />
          {itemsView === 'sheet' ? (
            <DatasetSpreadsheet
              items={items}
              datasetId={dsId}
              loading={itemsQ.isLoading && !itemsQ.data}
              selectedIds={selectedSet}
              onToggle={toggleItem}
              allPageSelected={allPageSelected}
              onToggleAllPage={toggleAllPage}
            />
          ) : (
            <DataTable
              columns={itemCols}
              rows={items}
              rowKey="id"
              loading={itemsQ.isLoading && !itemsQ.data}
              refreshing={itemsQ.isFetching}
              emptyText="暂无样本，点右上「从日志采样」或「手工导入」开始"
              minWidth={720}
            />
          )}
          <TablePagination
            page={itemPage}
            pageSize={itemPageSize}
            total={itemsTotal}
            onPageChange={setItemPage}
            onPageSizeChange={s => {
              setItemPageSize(s);
              setItemPage(1);
            }}
          />
        </div>
      ) : (
        <div className="space-y-4">
          {(runsQ.data?.length ?? 0) > 0 && (
            <RunStatsOverview runs={runsQ.data ?? []} itemCount={dsQ.data?.item_count ?? 0} />
          )}
          <DataTable
            columns={runCols}
            rows={sortRuns(runsQ.data ?? [], runSort)}
            rowKey="id"
            leftBar={r => statusBar(r.status)}
            loading={runsQ.isLoading}
            onRowClick={r => navigate(`/datasets/${dsId}/runs/${r.id}`)}
            sortKey={runSort.key}
            sortOrder={runSort.order}
            onSortChange={(key, order) => setRunSort({ key, order })}
            emptyText="还没有运行；点右上「新建评估」跑一次会出现在这里"
            minWidth={620}
          />
        </div>
      )}

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
      {aiGenOpen && (
        <AiGenerateModal
          datasetId={dsId}
          onClose={() => setAiGenOpen(false)}
          onDone={() => {
            refreshAll();
            setAiGenOpen(false);
          }}
        />
      )}
      {evalOpen && (
        <NewEvaluationWizard
          presetDatasetId={dsId}
          judges={judgesQ.data}
          onClose={() => setEvalOpen(false)}
          onRunStarted={(_dsId, run) =>
            navigate(`/datasets/${dsId}/runs/${run.id}`)
          }
          onJobCreated={() => navigate('/eval-jobs')}
        />
      )}
    </div>
  );
};

function sortRuns(
  rows: DatasetRunRow[],
  sort: { key: string; order: 'asc' | 'desc' },
): DatasetRunRow[] {
  const dir = sort.order === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    let c: number;
    if (sort.key === 'score') {
      c = (runScore(a) ?? -1) - (runScore(b) ?? -1);
    } else if (sort.key === 'status') {
      c = a.status.localeCompare(b.status);
    } else if (sort.key === 'name') {
      c = a.name.localeCompare(b.name);
    } else {
      c = a.created_at.localeCompare(b.created_at);
    }
    return c * dir;
  });
}

const statusBar = (s: string): string =>
  s === 'success' ? 'bg-emerald-400' : s === 'failed' ? 'bg-rose-400' : 'bg-stone-300';

function sampledAt(item: DatasetItemRow): unknown {
  const meta = item.meta as Record<string, unknown> | null;
  return meta?.sampled_at ?? meta?.imported_at ?? item.created_at;
}

/** 评分方案库 —— 多 metric 加权评测模板的 CRUD + onboarding + 应用数。
 *
 * 「评分方案」= 复用的多指标 / judge 打分配置；建好后在「新建评估」/「定时任务」里选它。
 */

import {
  keepPreviousData,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { Pencil, Plus, Ruler, Trash2 } from 'lucide-react';
import { useState } from 'react';

import {
  DataTable,
  type DataTableColumn,
  TablePagination,
  TableToolbar,
} from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { confirm } from '@/core/lib/confirm';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { EvalTemplateFormModal } from '@/system/datasets/components/eval-template-form-modal';
import { SchemeLibraryOnboarding } from '@/system/datasets/components/scheme-library-onboarding';
import { evalTemplateApi } from '@/system/datasets/services/eval-template';
import type {
  CreateEvalTemplateRequest,
  EvalTemplateItem,
  UpdateEvalTemplateRequest,
} from '@/system/datasets/types/eval-template';

export const EvalTemplatesPage = () => {
  const qc = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<EvalTemplateItem | null>(null);
  const [sortKey, setSortKey] = useState('updated_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');
  const [kwInput, setKwInput] = useState('');
  const resetPage = () => setPage(1);

  const listQ = useQuery({
    queryKey: [
      'eval-templates',
      'list',
      page,
      pageSize,
      keyword,
      sortKey,
      sortOrder,
    ],
    queryFn: () =>
      evalTemplateApi.list({
        page,
        page_size: pageSize,
        keyword: keyword || undefined,
        sort_by: sortKey,
        order: sortOrder,
      }),
    placeholderData: keepPreviousData,
  });

  const visibleRows = listQ.data?.items ?? [];
  const usageQueries = useQueries({
    queries: visibleRows.map(t => ({
      queryKey: ['eval-template-usage', String(t.id)],
      queryFn: () => evalTemplateApi.usageCount(t.id),
      staleTime: 30_000,
    })),
  });
  const usageById = new Map<string, number>();
  visibleRows.forEach((t, i) => {
    const c = usageQueries[i]?.data?.job_count;
    if (typeof c === 'number') usageById.set(String(t.id), c);
  });

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ['eval-templates'] });

  const closeForm = () => {
    setFormOpen(false);
    setEditTarget(null);
  };

  const createMut = useMutation({
    mutationFn: (req: CreateEvalTemplateRequest) => evalTemplateApi.create(req),
    onSuccess: () => {
      toast.success('已创建');
      invalidate();
      closeForm();
    },
    onError: (e: unknown) =>
      toast.error((e as { message?: string })?.message || '创建失败'),
  });
  const updateMut = useMutation({
    mutationFn: ({
      id,
      req,
    }: {
      id: EntityId;
      req: UpdateEvalTemplateRequest;
    }) => evalTemplateApi.update(id, req),
    onSuccess: () => {
      toast.success('已保存（版本 +1）');
      invalidate();
      closeForm();
    },
    onError: (e: unknown) =>
      toast.error((e as { message?: string })?.message || '保存失败'),
  });
  const deleteMut = useMutation({
    mutationFn: (id: EntityId) => evalTemplateApi.delete(id),
    onSuccess: () => {
      toast.success('已删除');
      invalidate();
    },
  });

  const openCreate = () => {
    setEditTarget(null);
    setFormOpen(true);
  };
  const openEdit = (t: EvalTemplateItem) => {
    setEditTarget(t);
    setFormOpen(true);
  };

  const handleDelete = async (t: EvalTemplateItem) => {
    const ok = await confirm({
      title: `删除评分方案「${t.name}」？`,
      description:
        '已绑定该方案的评测任务按版本 freeze 不受影响；此操作不可恢复。',
      confirmText: '删除',
      danger: true,
    });
    if (ok) deleteMut.mutate(t.id);
  };

  const handleSubmit = (
    payload: CreateEvalTemplateRequest | UpdateEvalTemplateRequest,
  ) => {
    if (editTarget) {
      updateMut.mutate({
        id: editTarget.id,
        req: payload as UpdateEvalTemplateRequest,
      });
    } else {
      createMut.mutate(payload as CreateEvalTemplateRequest);
    }
  };

  const cols: DataTableColumn<EvalTemplateItem>[] = [
    {
      key: 'name',
      header: '方案',
      sortable: true,
      render: t => (
        <div className="min-w-0">
          <div className="truncate font-medium text-stone-800">{t.name}</div>
          {t.description && (
            <div className="truncate text-[11px] text-stone-400">
              {t.description}
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'metrics',
      header: '评分指标',
      render: t => (
        <div className="flex flex-wrap gap-1">
          {t.metrics.slice(0, 4).map((m, i) => (
            <span
              key={i}
              className="rounded bg-stone-100 px-1.5 py-0.5 text-[10.5px] text-stone-600"
              title={`${m.algorithm} · 权重 ${m.weight}${
                m.threshold != null ? ` · 阈值 ${m.threshold}` : ''
              }`}
            >
              {m.name}
              <span className="ml-1 text-stone-400">×{m.weight}</span>
            </span>
          ))}
          {t.metrics.length > 4 && (
            <span className="text-[10.5px] text-stone-400">
              +{t.metrics.length - 4}
            </span>
          )}
        </div>
      ),
    },
    {
      key: 'judge_provider',
      header: '评判模型',
      width: 140,
      render: t =>
        t.judge_provider ? (
          <span className="text-[11.5px] text-stone-600">
            {t.judge_provider}
          </span>
        ) : (
          <span className="text-stone-300">—</span>
        ),
    },
    {
      key: 'usage',
      header: '应用数',
      align: 'right',
      width: 76,
      render: t => {
        const count = usageById.get(String(t.id));
        if (count === undefined) {
          return <span className="text-[10.5px] text-stone-300">…</span>;
        }
        return count > 0 ? (
          <Badge
            variant="outline"
            className="bg-emerald-50 text-[10.5px] text-emerald-700"
            title="绑定该方案的定时评测任务数"
          >
            {count} 个任务
          </Badge>
        ) : (
          <span className="text-[10.5px] text-stone-400">未使用</span>
        );
      },
    },
    {
      key: 'version',
      header: '版本',
      align: 'right',
      width: 64,
      sortable: true,
      render: t => (
        <Badge variant="outline" className="text-[10.5px] text-stone-500">
          v{t.version}
        </Badge>
      ),
    },
    {
      key: 'updated_at',
      header: '更新时间',
      align: 'right',
      width: 160,
      sortable: true,
      render: t => (
        <span className="text-[11.5px] text-stone-500">
          {formatDateTime(t.updated_at)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      width: 80,
      render: t => (
        <div className="flex items-center justify-end gap-0.5">
          <button
            type="button"
            onClick={e => {
              e.stopPropagation();
              openEdit(t);
            }}
            title="编辑"
            className="rounded p-1 text-stone-400 hover:bg-stone-100 hover:text-stone-700"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={e => {
              e.stopPropagation();
              handleDelete(t);
            }}
            title="删除"
            className="rounded p-1 text-stone-400 hover:bg-rose-50 hover:text-rose-600"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ),
    },
  ];

  const rows = listQ.data?.items ?? [];
  const total = listQ.data?.total ?? 0;

  return (
    <div>
      <SchemeLibraryOnboarding total={total} loading={listQ.isLoading} />

      <TableToolbar
        title={
          <span className="flex items-center gap-2">
            <Ruler className="h-4 w-4 text-stone-500" />
            评分方案
            <span className="text-[11px] font-normal text-stone-400">
              {total} 个
            </span>
          </span>
        }
        onRefresh={() => listQ.refetch()}
        search={{
          value: kwInput,
          onChange: setKwInput,
          onSubmit: v => {
            setKeyword(v);
            resetPage();
          },
          placeholder: '搜索方案名称',
        }}
        extra={
          <Button size="sm" onClick={openCreate}>
            <Plus className="mr-1 h-3.5 w-3.5" /> 新建方案
          </Button>
        }
      />

      <DataTable
        columns={cols}
        rows={rows}
        rowKey="id"
        sortKey={sortKey}
        sortOrder={sortOrder}
        onSortChange={(k, o) => {
          setSortKey(k);
          setSortOrder(o);
          resetPage();
        }}
        loading={listQ.isLoading && !listQ.data}
        refreshing={listQ.isFetching}
        onRowClick={openEdit}
        emptyText="暂无评分方案，点右上「新建方案」开始；建好后在「新建评估」/「定时任务」里选它"
        emptyExtra={
          <Button size="sm" variant="secondary" onClick={openCreate}>
            新建方案
          </Button>
        }
      />

      <TablePagination
        page={page}
        pageSize={pageSize}
        total={total}
        onPageChange={setPage}
        onPageSizeChange={s => {
          setPageSize(s);
          resetPage();
        }}
      />

      {formOpen && (
        <EvalTemplateFormModal
          key={editTarget?.id ?? 'create'}
          open
          initial={editTarget}
          loading={createMut.isPending || updateMut.isPending}
          onClose={closeForm}
          onSubmit={handleSubmit}
        />
      )}
    </div>
  );
};

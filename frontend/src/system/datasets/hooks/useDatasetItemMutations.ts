/** 电子表格样本增删改的 mutation 集合（乐观更新 + 回滚 + item_count 维护）。
 *
 *  query key 约定：['datasets', dsId, 'items', ...]（分页行数据，含 page/pageSize）+
 *  ['datasets', dsId]（item_count 角标）。乐观更新跨所有分页页缓存匹配。 */
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { toast } from '@/core/lib/toast';
import type { EntityId, PageResult } from '@/core/types/api';
import { datasetApi } from '@/system/datasets/services/dataset';
import type {
  CreateItemRequest,
  DatasetItemRow,
  UpdateItemRequest,
} from '@/system/datasets/types/dataset';

interface UpdateArgs {
  itemId: EntityId;
  req: UpdateItemRequest;
}

type ItemsPage = PageResult<DatasetItemRow>;

interface OptimisticContext {
  /** 受影响的分页缓存快照（key 序列化 → 旧值），出错整体回滚。 */
  snapshots: [readonly unknown[], ItemsPage | undefined][];
}

export const useDatasetItemMutations = (datasetId: EntityId) => {
  const qc = useQueryClient();
  const itemsKey = ['datasets', datasetId, 'items'] as const;
  const dsKey = ['datasets', datasetId] as const;

  const invalidateItems = () => void qc.invalidateQueries({ queryKey: itemsKey });
  const invalidateCount = () => void qc.invalidateQueries({ queryKey: dsKey });

  /** 对所有分页页缓存（itemsKey 前缀）应用一个行变换函数。 */
  const mutatePages = (
    transform: (rows: DatasetItemRow[]) => DatasetItemRow[],
  ): OptimisticContext['snapshots'] => {
    const snapshots: OptimisticContext['snapshots'] = [];
    const entries = qc.getQueriesData<ItemsPage>({ queryKey: itemsKey });
    for (const [key, page] of entries) {
      snapshots.push([key, page]);
      if (!page) continue;
      qc.setQueryData<ItemsPage>(key, { ...page, items: transform(page.items) });
    }
    return snapshots;
  };

  const rollback = (snapshots: OptimisticContext['snapshots'] | undefined) => {
    snapshots?.forEach(([key, prev]) => qc.setQueryData(key, prev));
  };

  const update = useMutation<DatasetItemRow, unknown, UpdateArgs, OptimisticContext>({
    mutationFn: ({ itemId, req }) => datasetApi.updateItem(itemId, req),
    onMutate: async ({ itemId, req }) => {
      await qc.cancelQueries({ queryKey: itemsKey });
      const snapshots = mutatePages(rows =>
        rows.map(r =>
          r.id === itemId
            ? {
                ...r,
                ...(req.input_payload != null ? { input_payload: req.input_payload } : {}),
                ...(req.expected_output !== undefined
                  ? { expected_output: req.expected_output }
                  : {}),
                ...(req.meta !== undefined ? { meta: req.meta } : {}),
                ...(req.note !== undefined ? { note: req.note || null } : {}),
              }
            : r,
        ),
      );
      return { snapshots };
    },
    onError: (e, _vars, ctx) => {
      rollback(ctx?.snapshots);
      toast.error((e as { message?: string })?.message || '保存失败');
    },
    onSuccess: () => toast.success('已保存'),
    onSettled: invalidateItems,
  });

  const create = useMutation<DatasetItemRow, unknown, CreateItemRequest>({
    mutationFn: req => datasetApi.createItem(datasetId, req),
    onError: (e: unknown) => toast.error((e as { message?: string })?.message || '新增失败'),
    onSuccess: () => {
      invalidateItems();
      invalidateCount();
    },
  });

  const remove = useMutation<void, unknown, EntityId>({
    mutationFn: itemId => datasetApi.deleteItem(itemId),
    onError: (e: unknown) => toast.error((e as { message?: string })?.message || '删除失败'),
    onSuccess: () => {
      toast.success('已删除');
      invalidateItems();
      invalidateCount();
    },
  });

  const batchRemove = useMutation<{ deleted: number }, unknown, EntityId[]>({
    mutationFn: itemIds => datasetApi.batchDeleteItems(datasetId, { item_ids: itemIds }),
    onError: (e: unknown) => toast.error((e as { message?: string })?.message || '批量删除失败'),
    onSuccess: data => {
      toast.success(`已删除 ${data.deleted} 条样本`);
      invalidateItems();
      invalidateCount();
    },
  });

  return { update, create, remove, batchRemove };
};

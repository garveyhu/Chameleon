/** 电子表格样本增删改的 mutation 集合（乐观更新 + 回滚 + item_count 维护）。
 *
 *  query key 约定：['datasets', dsId, 'items']（行数据）+ ['datasets', dsId]（item_count 角标）。 */
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
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

interface UpdateContext {
  prev: DatasetItemRow[] | undefined;
}

export const useDatasetItemMutations = (datasetId: EntityId) => {
  const qc = useQueryClient();
  const itemsKey = ['datasets', datasetId, 'items'] as const;
  const dsKey = ['datasets', datasetId] as const;

  const invalidateCount = () => {
    void qc.invalidateQueries({ queryKey: dsKey });
  };

  const update = useMutation<DatasetItemRow, unknown, UpdateArgs, UpdateContext>({
    mutationFn: ({ itemId, req }) => datasetApi.updateItem(itemId, req),
    onMutate: async ({ itemId, req }) => {
      await qc.cancelQueries({ queryKey: itemsKey });
      const prev = qc.getQueryData<DatasetItemRow[]>(itemsKey);
      qc.setQueryData<DatasetItemRow[]>(itemsKey, rows =>
        (rows ?? []).map(r =>
          r.id === itemId
            ? {
                ...r,
                ...(req.input_payload != null ? { input_payload: req.input_payload } : {}),
                ...(req.expected_output !== undefined
                  ? { expected_output: req.expected_output }
                  : {}),
                ...(req.meta !== undefined ? { meta: req.meta } : {}),
              }
            : r,
        ),
      );
      return { prev };
    },
    onError: (e, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(itemsKey, ctx.prev);
      toast.error((e as { message?: string })?.message || '保存失败');
    },
    onSuccess: () => toast.success('已保存'),
    onSettled: () => void qc.invalidateQueries({ queryKey: itemsKey }),
  });

  const create = useMutation<DatasetItemRow, unknown, CreateItemRequest>({
    mutationFn: req => datasetApi.createItem(datasetId, req),
    onError: (e: unknown) => toast.error((e as { message?: string })?.message || '新增失败'),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: itemsKey });
      invalidateCount();
    },
  });

  const remove = useMutation<void, unknown, EntityId>({
    mutationFn: itemId => datasetApi.deleteItem(itemId),
    onError: (e: unknown) => toast.error((e as { message?: string })?.message || '删除失败'),
    onSuccess: () => {
      toast.success('已删除');
      void qc.invalidateQueries({ queryKey: itemsKey });
      invalidateCount();
    },
  });

  return { update, create, remove };
};

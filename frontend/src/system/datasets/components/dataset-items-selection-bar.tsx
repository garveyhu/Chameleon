/** 样本多选工具条 —— 「已选 N 条 / 删除已选 / 清空」，两视图（表格 + 电子表格）共用。
 *
 *  selectedCount 为 0 时整体不渲染，避免占位抖动。 */
import { Trash2 } from 'lucide-react';

import { Button } from '@/core/components/ui/button';

interface Props {
  selectedCount: number;
  deleting?: boolean;
  onClear: () => void;
  onDelete: () => void;
}

export const DatasetItemsSelectionBar = ({
  selectedCount,
  deleting,
  onClear,
  onDelete,
}: Props) => {
  if (selectedCount === 0) return null;

  return (
    <div className="flex items-center gap-2 rounded-md border border-stone-200 bg-stone-50 px-3 py-1.5 text-[12px]">
      <span className="text-stone-600">已选 {selectedCount} 条样本</span>
      <span className="ml-auto" />
      <Button size="sm" variant="ghost" onClick={onClear}>
        清空
      </Button>
      <Button size="sm" variant="danger" disabled={deleting} onClick={onDelete}>
        <Trash2 className="mr-1 h-3.5 w-3.5" />
        {deleting ? '删除中…' : '删除已选'}
      </Button>
    </div>
  );
};

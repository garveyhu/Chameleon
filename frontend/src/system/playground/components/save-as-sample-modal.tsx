/** 存为评测样本 —— playground 单条对话 → DatasetItem（复用 bulk-import）。
 *  H1：打通「调试 → 评测集」流转，调好的对话一键沉淀成评测样本。 */

import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { Button } from '@/core/components/ui/button';
import {
  Modal,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { datasetApi } from '@/system/datasets/services/dataset';

interface Props {
  defaultInput: string;
  defaultExpected: string;
  onClose: () => void;
}

export const SaveAsSampleModal = ({
  defaultInput,
  defaultExpected,
  onClose,
}: Props) => {
  const [datasetId, setDatasetId] = useState<EntityId | ''>('');
  const [input, setInput] = useState(defaultInput);
  const [expected, setExpected] = useState(defaultExpected);

  const dsQ = useQuery({
    queryKey: ['datasets', 'all-for-save'],
    queryFn: () => datasetApi.list({ page: 1, page_size: 100 }),
  });
  const datasets = dsQ.data?.items ?? [];

  const mut = useMutation({
    mutationFn: () =>
      datasetApi.bulkImport(datasetId as EntityId, {
        items: [
          {
            input_payload: { user_input: input },
            expected_output: expected.trim() ? { answer: expected } : null,
          },
        ],
      }),
    onSuccess: () => {
      toast.success('已存为评测样本');
      onClose();
    },
    onError: (e: unknown) =>
      toast.error((e as { message?: string })?.message || '保存失败'),
  });

  const save = () => {
    if (!datasetId) {
      toast.error('请选择目标数据集');
      return;
    }
    if (!input.trim()) {
      toast.error('输入不能为空');
      return;
    }
    mut.mutate();
  };

  return (
    <Modal open onOpenChange={o => !o && onClose()}>
      <ModalContent>
        <ModalHeader>
          <ModalTitle>存为评测样本</ModalTitle>
        </ModalHeader>
        <div className="space-y-3 px-4 py-3 text-[12.5px]">
          <div>
            <div className="mb-1 text-[11.5px] text-stone-600">目标数据集</div>
            <div className="max-h-[140px] space-y-1 overflow-auto rounded-md border border-stone-200 p-1">
              {dsQ.isLoading ? (
                <div className="px-2 py-2 text-[11px] text-stone-400">加载中…</div>
              ) : datasets.length === 0 ? (
                <div className="px-2 py-2 text-[11px] text-stone-400">
                  暂无数据集，先去「数据集」页新建
                </div>
              ) : (
                datasets.map(d => (
                  <button
                    key={String(d.id)}
                    type="button"
                    onClick={() => setDatasetId(d.id)}
                    className={cn(
                      'flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-[12px] transition',
                      datasetId === d.id
                        ? 'bg-stone-800 text-white'
                        : 'text-stone-700 hover:bg-stone-100',
                    )}
                  >
                    <span className="truncate">{d.name}</span>
                    <span
                      className={cn(
                        'ml-2 shrink-0 text-[10.5px]',
                        datasetId === d.id ? 'text-stone-300' : 'text-stone-400',
                      )}
                    >
                      {d.item_count} 样本
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>
          <div>
            <label className="mb-1 block text-[11.5px] text-stone-600">
              输入（问题）
            </label>
            <Textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              rows={2}
              className="text-[12px]"
            />
          </div>
          <div>
            <label className="mb-1 block text-[11.5px] text-stone-600">
              理想回答
              <span className="ml-1 text-[10.5px] text-stone-400">
                可留空后续在数据集里标注
              </span>
            </label>
            <Textarea
              value={expected}
              onChange={e => setExpected(e.target.value)}
              rows={4}
              className="text-[12px]"
            />
          </div>
        </div>
        <ModalFooter>
          <Button variant="ghost" size="sm" onClick={onClose}>
            取消
          </Button>
          <Button size="sm" disabled={mut.isPending} onClick={save}>
            {mut.isPending ? '保存中…' : '保存'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

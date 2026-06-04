/** AI 扩样 —— 种子样本 + 任务描述 → LLM 批量生成新评测样本。H2 批量阶段。 */

import { useMutation } from '@tanstack/react-query';
import { Loader2, Sparkles } from 'lucide-react';
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
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { datasetApi } from '@/system/datasets/services/dataset';
import type { AiGenerateResult } from '@/system/datasets/types/dataset';

interface Props {
  datasetId: EntityId;
  onClose: () => void;
  onDone: () => void;
}

export const AiGenerateModal = ({ datasetId, onClose, onDone }: Props) => {
  const [task, setTask] = useState('');
  const [count, setCount] = useState(5);

  const mut = useMutation({
    mutationFn: () =>
      datasetApi.aiGenerate(datasetId, { task_description: task, count }),
    onSuccess: (d: AiGenerateResult) => {
      toast.success(`AI 已生成 ${d.added} 条样本`);
      onDone();
    },
    onError: (e: unknown) =>
      toast.error((e as { message?: string })?.message || '生成失败'),
  });

  const run = () => {
    if (!task.trim()) {
      toast.error('请填写生成任务描述');
      return;
    }
    mut.mutate();
  };

  return (
    <Modal open onOpenChange={o => !o && onClose()}>
      <ModalContent>
        <ModalHeader>
          <ModalTitle>AI 扩样</ModalTitle>
        </ModalHeader>
        <div className="space-y-3 px-4 py-3 text-[12.5px]">
          <p className="text-[10.5px] leading-snug text-stone-400">
            以本数据集现有样本为风格参照，让 AI 仿照批量生成新样本（走评测渠道，
            成本计入 Trace）。
          </p>
          <div>
            <label className="mb-1 block text-[11.5px] text-stone-600">
              生成任务描述
            </label>
            <Textarea
              value={task}
              onChange={e => setTask(e.target.value)}
              rows={3}
              placeholder="如：生成 Python 进阶知识点的问答样本，覆盖装饰器、生成器、异步等主题"
              className="text-[12px]"
            />
          </div>
          <div>
            <label className="mb-1 block text-[11.5px] text-stone-600">
              生成数量
            </label>
            <input
              type="number"
              min={1}
              max={50}
              value={count}
              onChange={e =>
                setCount(Math.max(1, Math.min(50, Number(e.target.value) || 1)))
              }
              className="w-24 rounded-md border border-stone-200 px-2 py-1.5 text-[12.5px]"
            />
            <span className="ml-2 text-[10.5px] text-stone-400">1–50 条</span>
          </div>
        </div>
        <ModalFooter>
          <Button variant="ghost" size="sm" onClick={onClose}>
            取消
          </Button>
          <Button size="sm" disabled={mut.isPending} onClick={run}>
            {mut.isPending ? (
              <>
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> 生成中…
              </>
            ) : (
              <>
                <Sparkles className="mr-1 h-3.5 w-3.5" /> 开始生成
              </>
            )}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

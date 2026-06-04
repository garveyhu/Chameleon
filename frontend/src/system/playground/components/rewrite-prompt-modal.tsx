/** 基于回答改写 System Prompt —— 轻量即时改写（H1）。
 *
 * 取该列当前 System Prompt + 这条不理想回答 + 用户改写诉求 → 调后端 channel='eval'
 * 单次 LLM 改写 → 预览旧/新对比 → 应用回灌 ParamPanel。不落任何库（即时改写）。
 *
 * 与 H3 optimizer 区分：optimizer 是 run 级 / 整集低分共性 / 落库版本链；此处单条 / 即时。
 */

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
import { toast } from '@/core/lib/toast';
import { paramsOf, useChatStore } from '@/core/stores/chat';
import { modelApi } from '@/system/models/services/model';
import { rewritePrompt } from '@/system/playground/services/playground';

interface Props {
  columnId: string;
  answer: string;
  onClose: () => void;
}

export const RewritePromptModal = ({ columnId, answer, onClose }: Props) => {
  const params = useChatStore(s => paramsOf(s, columnId));
  const updateParams = useChatStore(s => s.updateParams);

  const [instruction, setInstruction] = useState('');
  const [rewritten, setRewritten] = useState<string | null>(null);

  const modelsQ = useQuery({
    queryKey: ['playground-models'],
    queryFn: () => modelApi.list({ kind: 'chat' }),
  });

  const currentPrompt = params?.system_prompt ?? '';
  // model_id（雪花 string）→ code；后端按 model_code 容错，None 兜底默认模型
  const modelCode =
    (modelsQ.data ?? []).find(m => String(m.id) === String(params?.model_id))?.code ??
    null;

  const mut = useMutation({
    mutationFn: () =>
      rewritePrompt({
        current_prompt: currentPrompt,
        answer,
        instruction: instruction.trim(),
        model_code: modelCode,
      }),
    onSuccess: res => setRewritten(res.rewritten_prompt),
    onError: (e: unknown) =>
      toast.error((e as { message?: string })?.message || '改写失败'),
  });

  const submit = () => {
    if (!instruction.trim()) {
      toast.error('请填写改写诉求');
      return;
    }
    mut.mutate();
  };

  const apply = () => {
    if (!params || rewritten == null) return;
    updateParams(columnId, { ...params, system_prompt: rewritten });
    toast.success('已更新 System Prompt');
    onClose();
  };

  return (
    <Modal open onOpenChange={o => !o && onClose()}>
      <ModalContent>
        <ModalHeader>
          <ModalTitle>基于此回答改写 System Prompt</ModalTitle>
        </ModalHeader>
        <div className="space-y-3 px-4 py-3 text-[12.5px]">
          <div>
            <label className="mb-1 block text-[11.5px] text-stone-600">改写诉求</label>
            <Textarea
              value={instruction}
              onChange={e => setInstruction(e.target.value)}
              rows={3}
              placeholder="如：让回答更简短、给出引用来源、用更专业的语气"
              className="text-[12px]"
              autoFocus
            />
          </div>

          {rewritten != null && (
            <div className="space-y-2">
              <div>
                <div className="mb-1 text-[11.5px] text-stone-500">原 System Prompt</div>
                <div className="max-h-[120px] overflow-auto whitespace-pre-wrap rounded-md border border-stone-200 bg-stone-50 px-2 py-1.5 text-[11.5px] text-stone-500">
                  {currentPrompt || '（空）'}
                </div>
              </div>
              <div>
                <div className="mb-1 text-[11.5px] text-emerald-600">改写后</div>
                <div className="max-h-[160px] overflow-auto whitespace-pre-wrap rounded-md border border-emerald-200 bg-emerald-50/60 px-2 py-1.5 text-[12px] text-stone-800">
                  {rewritten}
                </div>
              </div>
              <p className="text-[10.5px] text-stone-400">
                应用后将覆盖当前 System Prompt，可在参数面板手动改回
              </p>
            </div>
          )}
        </div>
        <ModalFooter>
          <Button variant="ghost" size="sm" onClick={onClose}>
            取消
          </Button>
          {rewritten == null ? (
            <Button size="sm" disabled={mut.isPending} onClick={submit}>
              {mut.isPending ? '改写中…' : '改写'}
            </Button>
          ) : (
            <>
              <Button
                variant="ghost"
                size="sm"
                disabled={mut.isPending}
                onClick={submit}
              >
                {mut.isPending ? '改写中…' : '重新改写'}
              </Button>
              <Button size="sm" onClick={apply}>
                应用
              </Button>
            </>
          )}
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

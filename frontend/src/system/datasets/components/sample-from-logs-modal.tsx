/** 从 call_log 采样 modal —— P21.1 PR #61 */

import { useMutation } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import {
  Modal,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import { datasetApi } from '@/system/datasets/services/dataset';
import type {
  PiiStrategy,
  SampleFromLogsRequest,
  SampleResult,
} from '@/system/datasets/types/dataset';

interface Props {
  datasetId: number;
  onClose: () => void;
  onDone: () => void;
}

export const SampleFromLogsModal = ({
  datasetId,
  onClose,
  onDone,
}: Props) => {
  const [agentKey, setAgentKey] = useState('');
  const [appId, setAppId] = useState('');
  const [limit, setLimit] = useState(50);
  const [piiStrategy, setPiiStrategy] = useState<PiiStrategy>('mask');
  const [includeExpected, setIncludeExpected] = useState(true);
  const [successOnly, setSuccessOnly] = useState(true);

  const sampleMut = useMutation({
    mutationFn: (req: SampleFromLogsRequest) =>
      datasetApi.sampleFromLogs(datasetId, req),
    onSuccess: (data: SampleResult) => {
      toast.success(
        `采样完成：新增 ${data.added}，跳过 ${data.skipped}，PII drop ${data.dropped_pii}`,
      );
      onDone();
    },
    onError: e =>
      toast.error('采样失败：' + (e as Error).message),
  });

  return (
    <Modal open onOpenChange={open => !open && onClose()}>
      <ModalContent>
        <ModalHeader>
          <ModalTitle>从调用日志采样</ModalTitle>
        </ModalHeader>
        <div className="space-y-3 px-4 py-3 text-[12.5px]">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[11.5px] text-stone-600">
                agent_key（可选）
              </label>
              <Input
                value={agentKey}
                onChange={e => setAgentKey(e.target.value)}
                placeholder="qwen-chat / example"
                className="font-mono text-[12px]"
              />
            </div>
            <div>
              <label className="mb-1 block text-[11.5px] text-stone-600">
                app_id（可选）
              </label>
              <Input
                value={appId}
                onChange={e => setAppId(e.target.value)}
                placeholder="留空 = 所有 app"
                className="font-mono text-[12px]"
              />
            </div>
            <div>
              <label className="mb-1 block text-[11.5px] text-stone-600">
                采样上限（1-500）
              </label>
              <Input
                type="number"
                min={1}
                max={500}
                value={limit}
                onChange={e =>
                  setLimit(
                    Math.max(1, Math.min(500, Number(e.target.value) || 50)),
                  )
                }
                className="text-[12px]"
              />
            </div>
            <div>
              <label className="mb-1 block text-[11.5px] text-stone-600">
                PII 策略
              </label>
              <div className="flex gap-1">
                {(['mask', 'drop', 'keep'] as const).map(opt => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setPiiStrategy(opt)}
                    className={cn(
                      'flex-1 rounded-md border px-2 py-1 text-[11.5px] transition',
                      piiStrategy === opt
                        ? 'border-amber-300 bg-amber-50 text-amber-700'
                        : 'border-stone-200 bg-white text-stone-600 hover:bg-stone-50',
                    )}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="flex gap-4 pt-1">
            <label className="flex items-center gap-2 text-[11.5px] text-stone-600">
              <input
                type="checkbox"
                checked={successOnly}
                onChange={e => setSuccessOnly(e.target.checked)}
              />
              仅成功调用
            </label>
            <label className="flex items-center gap-2 text-[11.5px] text-stone-600">
              <input
                type="checkbox"
                checked={includeExpected}
                onChange={e => setIncludeExpected(e.target.checked)}
              />
              response 作为 expected_output
            </label>
          </div>
          <div className="rounded-md bg-amber-50/60 px-2 py-1.5 text-[10.5px] leading-snug text-amber-700">
            红线（plan §2 P21）：采样必须脱敏；mask 默认替换 email/phone/id_card 为占位符；drop 含 PII 整条跳过。
          </div>
        </div>
        <ModalFooter>
          <Button variant="ghost" size="sm" onClick={onClose}>
            取消
          </Button>
          <Button
            size="sm"
            disabled={sampleMut.isPending}
            onClick={() =>
              sampleMut.mutate({
                agent_key: agentKey.trim() || undefined,
                app_id: appId.trim() || undefined,
                limit,
                pii_strategy: piiStrategy,
                include_response_as_expected: includeExpected,
                success: successOnly ? true : undefined,
              })
            }
          >
            {sampleMut.isPending && (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            )}
            开始采样
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

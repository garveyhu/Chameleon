/** 从调用日志采样 modal —— 把历史调用日志抽成评测样本 */

import { useMutation } from '@tanstack/react-query';
import { HelpCircle, Loader2 } from 'lucide-react';
import { useState } from 'react';

import { AgentPicker } from '@/core/components/common/agent-picker';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import {
  Modal,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { Tooltip } from '@/core/components/ui/tooltip';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import { datasetApi } from '@/system/datasets/services/dataset';
import type { EntityId } from '@/core/types/api';
import type {
  PiiStrategy,
  SampleFromLogsRequest,
  SampleResult,
} from '@/system/datasets/types/dataset';

interface Props {
  datasetId: EntityId;
  onClose: () => void;
  onDone: () => void;
}

/** PII 策略三态的人话说明（标签 + 一句话） */
const PII_OPTIONS: { value: PiiStrategy; label: string; hint: string }[] = [
  {
    value: 'mask',
    label: '打码',
    hint: '把邮箱 / 手机号 / 身份证等替换为占位符后保留（默认）',
  },
  {
    value: 'drop',
    label: '丢弃',
    hint: '含敏感信息的整条样本直接跳过，不入库',
  },
  {
    value: 'keep',
    label: '保留',
    hint: '原样保留，仅在明确无敏感信息时使用',
  },
];

const PII_TOOLTIP =
  '敏感信息（PII）指邮箱、手机号、身份证号等可识别到个人的信息。采样会按所选策略处理，避免把真实个人信息带入评测集。';

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
        `采样完成：新增 ${data.added} 条，跳过 ${data.skipped} 条，含敏感信息丢弃 ${data.dropped_pii} 条`,
      );
      onDone();
    },
    onError: e => toast.error('采样失败：' + (e as Error).message),
  });

  const activePii = PII_OPTIONS.find(o => o.value === piiStrategy);

  return (
    <Modal open onOpenChange={open => !open && onClose()}>
      <ModalContent>
        <ModalHeader>
          <ModalTitle>从调用日志采样</ModalTitle>
        </ModalHeader>
        <div className="space-y-3 px-4 py-3 text-[12.5px]">
          <p className="text-[11px] leading-snug text-stone-500">
            从历史调用日志里抽取真实请求 / 返回，自动整理成评测样本。
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[11.5px] text-stone-600">
                智能体
              </label>
              <AgentPicker value={agentKey} onChange={setAgentKey} width={232} />
              <p className="mt-1 text-[10.5px] leading-tight text-stone-400">
                选「全部应用」= 不限智能体
              </p>
            </div>
            <div>
              <label className="mb-1 block text-[11.5px] text-stone-600">
                应用 / 调用方（可选）
              </label>
              <Input
                value={appId}
                onChange={e => setAppId(e.target.value)}
                placeholder="留空 = 所有调用方"
                className="font-mono text-[12px]"
              />
              <p className="mt-1 text-[10.5px] leading-tight text-stone-400">
                按发起调用的应用筛选，留空不限
              </p>
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
              <label className="mb-1 flex items-center gap-1 text-[11.5px] text-stone-600">
                敏感信息脱敏（PII）
                <Tooltip content={PII_TOOLTIP}>
                  <HelpCircle className="h-3.5 w-3.5 cursor-help text-stone-400" />
                </Tooltip>
              </label>
              <div className="flex gap-1">
                {PII_OPTIONS.map(opt => (
                  <Tooltip key={opt.value} content={opt.hint}>
                    <button
                      type="button"
                      onClick={() => setPiiStrategy(opt.value)}
                      className={cn(
                        'flex-1 rounded-md border px-2 py-1 text-[11.5px] transition',
                        piiStrategy === opt.value
                          ? 'border-amber-300 bg-amber-50 text-amber-700'
                          : 'border-stone-200 bg-white text-stone-600 hover:bg-stone-50',
                      )}
                    >
                      {opt.label}
                    </button>
                  </Tooltip>
                ))}
              </div>
              {activePii ? (
                <p className="mt-1 text-[10.5px] leading-tight text-stone-400">
                  {activePii.hint}
                </p>
              ) : null}
            </div>
          </div>
          <div className="flex gap-4 pt-1">
            <label className="flex items-center gap-2 text-[11.5px] text-stone-600">
              <input
                type="checkbox"
                checked={successOnly}
                onChange={e => setSuccessOnly(e.target.checked)}
              />
              仅采样成功的调用
            </label>
            <label className="flex items-center gap-2 text-[11.5px] text-stone-600">
              <input
                type="checkbox"
                checked={includeExpected}
                onChange={e => setIncludeExpected(e.target.checked)}
              />
              用「调用返回」作为「预期输出」
            </label>
          </div>
          <div className="rounded-md bg-amber-50/60 px-2 py-1.5 text-[10.5px] leading-snug text-amber-700">
            采样必须脱敏：「打码」会把邮箱 / 手机号 / 身份证替换为占位符，「丢弃」会把含敏感信息的整条样本跳过。
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

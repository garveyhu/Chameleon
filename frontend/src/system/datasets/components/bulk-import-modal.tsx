/** 手工导入样本 modal
 *
 * 支持 JSONL（每行一个 JSON）或单一 JSON 数组；前端解析后调 bulk-import 接口。
 * 每条至少要有「输入」（input_payload）；可选「预期输出」/ meta。
 */

import { useMutation } from '@tanstack/react-query';
import { HelpCircle, Loader2 } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Button } from '@/core/components/ui/button';
import {
  Modal,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { Textarea } from '@/core/components/ui/textarea';
import { Tooltip } from '@/core/components/ui/tooltip';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import { datasetApi } from '@/system/datasets/services/dataset';
import type { EntityId } from '@/core/types/api';
import type {
  BulkImportItem,
  BulkImportResult,
  PiiStrategy,
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
  '敏感信息（PII）指邮箱、手机号、身份证号等可识别到个人的信息。导入会按所选策略处理，避免把真实个人信息带入评测集。';

const EXAMPLE = `# 每行一个 JSON（JSONL）或粘贴整个 JSON 数组
# input_payload = 输入（必填，对象）；expected_output = 预期输出（可选）
{"input_payload":{"q":"什么是 RAG？"},"expected_output":{"answer":"检索增强生成"}}
{"input_payload":{"q":"什么是 Agent？"},"expected_output":{"answer":"自主智能体"}}`;

export const BulkImportModal = ({ datasetId, onClose, onDone }: Props) => {
  const [text, setText] = useState('');
  const [piiStrategy, setPiiStrategy] = useState<PiiStrategy>('mask');

  const parsed = useMemo(() => parseInput(text), [text]);
  const activePii = PII_OPTIONS.find(o => o.value === piiStrategy);

  const importMut = useMutation({
    mutationFn: (items: BulkImportItem[]) =>
      datasetApi.bulkImport(datasetId, { items, pii_strategy: piiStrategy }),
    onSuccess: (data: BulkImportResult) => {
      toast.success(
        `导入完成：新增 ${data.added} 条，含敏感信息丢弃 ${data.dropped_pii} 条`,
      );
      onDone();
    },
    onError: e => toast.error('导入失败：' + (e as Error).message),
  });

  return (
    <Modal open onOpenChange={open => !open && onClose()}>
      <ModalContent>
        <ModalHeader>
          <ModalTitle>手工导入样本</ModalTitle>
        </ModalHeader>
        <div className="space-y-3 px-4 py-3 text-[12.5px]">
          <div>
            <label className="mb-1 block text-[11.5px] text-stone-600">
              样本内容（JSONL 或 JSON 数组）
            </label>
            <p className="mb-1 text-[10.5px] leading-snug text-stone-400">
              每行一个 JSON（JSONL），或粘贴整个 JSON 数组。每条至少包含「输入」
              （input_payload，对象）；「预期输出」（expected_output）/ meta 可选。
            </p>
            <Textarea
              value={text}
              onChange={e => setText(e.target.value)}
              placeholder={EXAMPLE}
              rows={10}
              className="font-mono text-[11.5px]"
            />
            <div className="mt-1 flex items-center justify-between text-[11px]">
              {parsed.ok ? (
                <span className="text-emerald-600">
                  解析成功 · 共 {parsed.items.length} 条
                </span>
              ) : (
                <span className="text-rose-600">解析失败：{parsed.error}</span>
              )}
              <span className="text-stone-400">支持 JSONL 或 JSON 数组</span>
            </div>
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
          <div className="rounded-md bg-amber-50/60 px-2 py-1.5 text-[10.5px] leading-snug text-amber-700">
            最多 1000 条 / 次；每条必须含「输入」（input_payload，对象）；「预期输出」/ meta 可选。
          </div>
        </div>
        <ModalFooter>
          <Button variant="ghost" size="sm" onClick={onClose}>
            取消
          </Button>
          <Button
            size="sm"
            disabled={
              !parsed.ok || parsed.items.length === 0 || importMut.isPending
            }
            onClick={() => parsed.ok && importMut.mutate(parsed.items)}
          >
            {importMut.isPending && (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            )}
            导入
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

interface ParseResult {
  ok: boolean;
  items: BulkImportItem[];
  error?: string;
}

function parseInput(raw: string): ParseResult {
  const text = raw.trim();
  if (!text) return { ok: false, items: [], error: '空内容' };

  // 先尝试整体当 JSON 数组
  try {
    const arr = JSON.parse(text);
    if (Array.isArray(arr)) {
      return validateItems(arr);
    }
    // 单个对象也接受
    if (typeof arr === 'object' && arr !== null) {
      return validateItems([arr]);
    }
  } catch {
    // fall through 到 JSONL
  }

  // JSONL：每行一个 JSON
  const items: unknown[] = [];
  const lines = text.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line || line.startsWith('#')) continue;
    try {
      items.push(JSON.parse(line));
    } catch (e) {
      return {
        ok: false,
        items: [],
        error: `第 ${i + 1} 行解析失败：${(e as Error).message}`,
      };
    }
  }
  return validateItems(items);
}

function validateItems(arr: unknown[]): ParseResult {
  const out: BulkImportItem[] = [];
  for (let i = 0; i < arr.length; i++) {
    const it = arr[i];
    if (!it || typeof it !== 'object') {
      return {
        ok: false,
        items: [],
        error: `第 ${i + 1} 条不是对象`,
      };
    }
    const obj = it as Record<string, unknown>;
    if (
      !obj.input_payload ||
      typeof obj.input_payload !== 'object' ||
      Array.isArray(obj.input_payload)
    ) {
      return {
        ok: false,
        items: [],
        error: `第 ${i + 1} 条「输入」（input_payload）必须是对象`,
      };
    }
    out.push({
      input_payload: obj.input_payload as Record<string, unknown>,
      expected_output: (obj.expected_output ?? null) as
        | Record<string, unknown>
        | null,
      meta: (obj.meta ?? null) as Record<string, unknown> | null,
    });
  }
  if (out.length > 1000) {
    return {
      ok: false,
      items: [],
      error: `条数超上限 1000（当前 ${out.length}）`,
    };
  }
  return { ok: true, items: out };
}

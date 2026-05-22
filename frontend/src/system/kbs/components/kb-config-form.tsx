/** KB 配置表单 —— 分块策略 / 召回参数 / 一键重分块 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { RotateCcw, Save } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import { documentApi } from '@/system/kbs/services/document';
import { kbApi } from '@/system/kbs/services/kb';
import type {
  KbChunkStrategy,
  KbItem,
  RecallMode,
} from '@/system/kbs/types/kb';

interface Props {
  kb: KbItem;
}

const MODES: { value: KbChunkStrategy['mode']; label: string; desc: string }[] = [
  { value: 'fixed', label: '固定字数', desc: '按 chunk_size 字数硬切，每段 overlap 字符' },
  { value: 'paragraph', label: '按段落', desc: '双换行切；单段超长再 fixed 二次切' },
  { value: 'sentence', label: '按句子', desc: '中英文句末标点切；单句超长再 fixed 二次切' },
  { value: 'regex', label: '自定义正则', desc: '用 separator_regex 切；单段超长再 fixed' },
  {
    value: 'token',
    label: '按 Token',
    desc: '模型感知 tiktoken 编码；chunk_size/overlap 单位为 token',
  },
];

export const KbConfigForm = ({ kb }: Props) => {
  const qc = useQueryClient();
  const [strategy, setStrategy] = useState<KbChunkStrategy>(() =>
    kb.chunk_strategy ?? {
      mode: 'fixed',
      chunk_size: kb.chunk_size,
      overlap: kb.chunk_overlap,
    },
  );
  const [topK, setTopK] = useState(kb.default_top_k);
  const [recallMode, setRecallMode] = useState<RecallMode>(kb.recall_mode);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const saveMut = useMutation({
    mutationFn: () =>
      kbApi.update(kb.id, {
        chunk_strategy: strategy,
        default_top_k: topK,
        recall_mode: recallMode,
      }),
    onSuccess: () => {
      toast.success('已保存');
      qc.invalidateQueries({ queryKey: ['kb', kb.id] });
      qc.invalidateQueries({ queryKey: ['kbs'] });
    },
  });

  const reindexMut = useMutation({
    mutationFn: () => documentApi.reindexAll(kb.id),
    onSuccess: queued => {
      toast.success(`已排队 ${queued.length} 个文档重分块`);
      qc.invalidateQueries({ queryKey: ['kb-documents', kb.id] });
      setConfirmOpen(false);
    },
  });

  const setMode = (mode: KbChunkStrategy['mode']) => {
    setStrategy(s => ({ ...s, mode }));
  };

  return (
    <div className="max-w-[640px] space-y-5">
      <section>
        <h3 className="mb-2 text-[13.5px] font-medium text-stone-900">分块策略</h3>
        <div className="grid grid-cols-5 gap-2">
          {MODES.map(m => (
            <button
              key={m.value}
              type="button"
              onClick={() => setMode(m.value)}
              className={cn(
                'rounded-md border px-3 py-2 text-left text-[12px] transition',
                strategy.mode === m.value
                  ? 'border-amber-400 bg-amber-50/60 text-amber-800'
                  : 'border-stone-200 bg-white text-stone-600 hover:border-stone-300',
              )}
            >
              <div className="font-medium">{m.label}</div>
              <div className="mt-0.5 text-[10.5px] leading-snug text-stone-500">
                {m.desc}
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="grid grid-cols-2 gap-4">
        <div>
          <label className="mb-1 block text-[12px] text-stone-600">
            chunk_size = <span className="font-mono tnum">{strategy.chunk_size ?? (strategy.mode === 'token' ? 512 : 800)}</span>
            <span className="ml-1 text-[10.5px] text-stone-400">
              {strategy.mode === 'token' ? 'token' : '字符'}
            </span>
          </label>
          <input
            type="range"
            min={strategy.mode === 'token' ? 64 : 100}
            max={strategy.mode === 'token' ? 2000 : 4000}
            step={strategy.mode === 'token' ? 32 : 100}
            value={strategy.chunk_size ?? (strategy.mode === 'token' ? 512 : 800)}
            onChange={e =>
              setStrategy(s => ({ ...s, chunk_size: Number(e.target.value) }))
            }
            className="w-full accent-amber-600"
          />
        </div>
        <div>
          <label className="mb-1 block text-[12px] text-stone-600">
            overlap = <span className="font-mono tnum">{strategy.overlap ?? (strategy.mode === 'token' ? 50 : 100)}</span>
            <span className="ml-1 text-[10.5px] text-stone-400">
              {strategy.mode === 'token' ? 'token' : '字符'}
            </span>
          </label>
          <input
            type="range"
            min={0}
            max={strategy.mode === 'token' ? 300 : 500}
            step={strategy.mode === 'token' ? 8 : 10}
            value={strategy.overlap ?? (strategy.mode === 'token' ? 50 : 100)}
            onChange={e =>
              setStrategy(s => ({ ...s, overlap: Number(e.target.value) }))
            }
            className="w-full accent-amber-600"
          />
        </div>
      </section>

      {strategy.mode === 'token' && (
        <section>
          <label className="mb-1 block text-[12px] text-stone-600">
            模型编码器 (model)
          </label>
          <Input
            value={strategy.model ?? ''}
            onChange={e =>
              setStrategy(s => ({ ...s, model: e.target.value || undefined }))
            }
            placeholder="留空使用 KB 的 embedding_model；可填 gpt-4o / qwen-plus 等"
            className="h-8 font-mono text-[12.5px]"
          />
          <div className="mt-1 text-[10.5px] text-stone-500">
            未知模型自动落回 cl100k_base 编码器（差异 ±5% 可忽略）
          </div>
        </section>
      )}

      {strategy.mode === 'regex' && (
        <section>
          <label className="mb-1 block text-[12px] text-stone-600">
            separator_regex
          </label>
          <Input
            value={strategy.separator_regex ?? ''}
            onChange={e =>
              setStrategy(s => ({ ...s, separator_regex: e.target.value }))
            }
            placeholder="\\n\\n+"
            className="h-8 font-mono text-[12.5px]"
          />
        </section>
      )}

      <section className="grid grid-cols-2 gap-4">
        <div>
          <label className="mb-1 block text-[12px] text-stone-600">
            默认 top_k = <span className="font-mono tnum">{topK}</span>
          </label>
          <input
            type="range"
            min={1}
            max={20}
            value={topK}
            onChange={e => setTopK(Number(e.target.value))}
            className="w-full accent-amber-600"
          />
        </div>
        <div>
          <label className="mb-1 block text-[12px] text-stone-600">召回模式</label>
          <Select
            value={recallMode}
            onValueChange={v => setRecallMode(v as RecallMode)}
          >
            <SelectTrigger className="h-8 text-[12.5px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="vector">vector（语义）</SelectItem>
              <SelectItem value="hybrid">hybrid（混合，Bundle 4 上线）</SelectItem>
              <SelectItem value="keyword">keyword（关键词，Bundle 4 上线）</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </section>

      <div className="flex justify-between border-t border-stone-200 pt-4">
        <Button
          variant="ghost"
          onClick={() => setConfirmOpen(true)}
          disabled={reindexMut.isPending}
        >
          <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
          应用并重分块所有文档
        </Button>
        <Button onClick={() => saveMut.mutate()} disabled={saveMut.isPending}>
          <Save className="mr-1.5 h-3.5 w-3.5" />
          保存配置
        </Button>
      </div>

      <Modal
        open={confirmOpen}
        onOpenChange={o => !o && setConfirmOpen(false)}
      >
        <ModalContent size="md">
          <ModalHeader>
            <ModalTitle>确认批量重分块</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <p className="text-[13px] text-stone-700">
              本操作会：
            </p>
            <ol className="ml-5 mt-2 list-decimal space-y-1 text-[12.5px] text-stone-600">
              <li>保存当前配置（chunk_strategy / top_k / recall_mode）</li>
              <li>对 KB 内所有已就绪 / 失败的文档清旧 chunks 并重新排 ingest 队列</li>
              <li>处理期间检索质量可能下降；新 chunks 完成前不会显示</li>
            </ol>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
              取消
            </Button>
            <Button
              onClick={async () => {
                await saveMut.mutateAsync();
                reindexMut.mutate();
              }}
              disabled={reindexMut.isPending || saveMut.isPending}
            >
              {reindexMut.isPending ? '排队中…' : '确认重分块'}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </div>
  );
};

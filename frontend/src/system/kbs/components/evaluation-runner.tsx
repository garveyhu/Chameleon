/** 新建评估 Modal —— 支持 jsonl 上传或表格录入 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Upload, X } from 'lucide-react';
import { useRef, useState } from 'react';

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
import { toast } from '@/core/lib/toast';
import { evaluationApi } from '@/system/kbs/services/evaluation';
import type {
  EvaluationQuery,
} from '@/system/kbs/types/evaluation';
import type { RecallMode } from '@/system/kbs/types/kb';

interface Props {
  open: boolean;
  onClose: () => void;
  kbId: import('@/core/types/api').EntityId;
}

interface QueryRow {
  query: string;
  expectedRaw: string; // 逗号分隔
}

export const EvaluationRunner = ({ open, onClose, kbId }: Props) => {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState('');
  const [mode, setMode] = useState<RecallMode>('vector');
  const [topK, setTopK] = useState(5);
  const [rows, setRows] = useState<QueryRow[]>([
    { query: '', expectedRaw: '' },
  ]);

  const reset = () => {
    setName('');
    setMode('vector');
    setTopK(5);
    setRows([{ query: '', expectedRaw: '' }]);
  };

  const handleJsonl = async (file: File) => {
    const text = await file.text();
    const lines = text.split('\n').filter(l => l.trim());
    const parsed: QueryRow[] = [];
    for (const line of lines) {
      try {
        const obj = JSON.parse(line) as {
          query?: string;
          expected_chunk_ids?: number[];
        };
        if (obj.query) {
          parsed.push({
            query: obj.query,
            expectedRaw: (obj.expected_chunk_ids ?? []).join(','),
          });
        }
      } catch {
        // skip malformed line
      }
    }
    if (parsed.length === 0) {
      toast.error('jsonl 解析失败：没有合法 query');
      return;
    }
    setRows(parsed);
    if (!name) setName(file.name.replace(/\.jsonl$/i, ''));
    toast.success(`已载入 ${parsed.length} 条 query`);
  };

  const buildQueries = (): EvaluationQuery[] => {
    return rows
      .filter(r => r.query.trim())
      .map(r => ({
        query: r.query.trim(),
        expected_chunk_ids: r.expectedRaw
          .split(/[,\s]+/)
          .map(s => Number(s.trim()))
          .filter(n => Number.isFinite(n) && n > 0),
      }));
  };

  const startMut = useMutation({
    mutationFn: () => {
      const queries = buildQueries();
      return evaluationApi.create(kbId, {
        name: name.trim(),
        queries,
        recall_mode: mode,
        top_k: topK,
      });
    },
    onSuccess: () => {
      toast.success('已开始评估');
      qc.invalidateQueries({ queryKey: ['kb-evaluations', kbId] });
      reset();
      onClose();
    },
  });

  const canSubmit =
    name.trim() && buildQueries().length > 0 && !startMut.isPending;

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="lg">
        <ModalHeader>
          <ModalTitle>新建评估批次</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-3">
              <label className="mb-1 block text-[12px] text-stone-600">
                批次名
              </label>
              <Input
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="如 2026-Q2 客户FAQ召回"
                className="h-8 text-[12.5px]"
              />
            </div>
            <div>
              <label className="mb-1 block text-[12px] text-stone-600">
                召回模式
              </label>
              <Select value={mode} onValueChange={v => setMode(v as RecallMode)}>
                <SelectTrigger className="h-8 text-[12.5px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="vector">vector</SelectItem>
                  <SelectItem value="hybrid">hybrid</SelectItem>
                  <SelectItem value="keyword">keyword</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-[12px] text-stone-600">
                top_k
              </label>
              <Input
                type="number"
                value={topK}
                min={1}
                max={50}
                onChange={e => setTopK(Math.max(1, Number(e.target.value)))}
                className="h-8 text-[12.5px]"
              />
            </div>
            <div className="flex items-end">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => fileRef.current?.click()}
              >
                <Upload className="mr-1.5 h-3.5 w-3.5" />
                导入 jsonl
              </Button>
              <input
                ref={fileRef}
                type="file"
                accept=".jsonl,.json,.txt"
                hidden
                onChange={e => {
                  const f = e.target.files?.[0];
                  if (f) handleJsonl(f);
                }}
              />
            </div>
          </div>

          <div className="rounded-md border border-stone-200">
            <div className="grid grid-cols-[1fr_240px_36px] gap-2 border-b border-stone-200 bg-stone-50/60 px-3 py-1.5 text-[11px] text-stone-500">
              <div>query</div>
              <div>expected_chunk_ids（逗号分隔）</div>
              <div />
            </div>
            <div className="max-h-[320px] overflow-y-auto">
              {rows.map((r, idx) => (
                <div
                  key={idx}
                  className="grid grid-cols-[1fr_240px_36px] gap-2 border-b border-stone-100 px-3 py-1.5 last:border-b-0"
                >
                  <Input
                    value={r.query}
                    onChange={e => {
                      const next = [...rows];
                      next[idx] = { ...next[idx], query: e.target.value };
                      setRows(next);
                    }}
                    className="h-7 text-[12.5px]"
                    placeholder="如何重置密码？"
                  />
                  <Input
                    value={r.expectedRaw}
                    onChange={e => {
                      const next = [...rows];
                      next[idx] = { ...next[idx], expectedRaw: e.target.value };
                      setRows(next);
                    }}
                    className="h-7 font-mono text-[12px]"
                    placeholder="1,2,3"
                  />
                  <button
                    type="button"
                    onClick={() => setRows(rows.filter((_, i) => i !== idx))}
                    disabled={rows.length === 1}
                    className="rounded p-1 text-stone-500 hover:bg-rose-50 hover:text-rose-600 disabled:opacity-30"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
            <div className="border-t border-stone-200 px-3 py-1.5">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setRows([...rows, { query: '', expectedRaw: '' }])}
              >
                <Plus className="mr-1 h-3 w-3" />
                添加 query
              </Button>
            </div>
          </div>
          <p className="text-[11px] text-stone-500">
            jsonl 示例：<code className="rounded bg-stone-100 px-1 font-mono">
              {`{"query":"如何退款","expected_chunk_ids":[12,38]}`}
            </code>
          </p>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button onClick={() => startMut.mutate()} disabled={!canSubmit}>
            开始评估
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

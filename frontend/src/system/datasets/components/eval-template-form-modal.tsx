/** 评分模板 创建/编辑 Modal —— 多 metric 加权配置（RAGAS 算子 + 内置）。
 *  编辑时模板名锁定：后端 update 自动 version+1，老 EvalJob 引用 freeze 不动。 */

import { Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
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
import type {
  CreateEvalTemplateRequest,
  EvalTemplateItem,
  MetricSpec,
  UpdateEvalTemplateRequest,
} from '@/system/datasets/types/eval-template';

const ALGO_OPTIONS: { value: string; label: string }[] = [
  { value: 'faithfulness', label: '忠实度 · faithfulness' },
  { value: 'answer_relevancy', label: '答案相关性 · answer_relevancy' },
  { value: 'context_precision', label: '上下文精确率 · context_precision' },
  { value: 'context_recall', label: '上下文召回率 · context_recall' },
  { value: 'answer_correctness', label: '答案正确性 · answer_correctness' },
  { value: 'exact_match', label: '精确匹配 · exact_match' },
  { value: 'semantic_similarity', label: '语义相似度 · semantic_similarity' },
];

interface MetricRow {
  _id: string;
  name: string;
  algorithm: string;
  weight: number;
  threshold: number | null;
}

const newRow = (): MetricRow => ({
  _id: crypto.randomUUID(),
  name: '',
  algorithm: 'faithfulness',
  weight: 1,
  threshold: null,
});

interface Props {
  open: boolean;
  initial?: EvalTemplateItem | null;
  loading: boolean;
  onClose: () => void;
  onSubmit: (
    payload: CreateEvalTemplateRequest | UpdateEvalTemplateRequest,
  ) => void;
}

export const EvalTemplateFormModal = ({
  open,
  initial,
  loading,
  onClose,
  onSubmit,
}: Props) => {
  const isEdit = !!initial;
  // 惰性初始化 + 父层 remount key（react-hooks/set-state-in-effect 禁副作用同步）
  const [name, setName] = useState(() => initial?.name ?? '');
  const [description, setDescription] = useState(
    () => initial?.description ?? '',
  );
  const [judgeProvider, setJudgeProvider] = useState(
    () => initial?.judge_provider ?? '',
  );
  const [rows, setRows] = useState<MetricRow[]>(() =>
    initial?.metrics.length
      ? initial.metrics.map(m => ({
          _id: crypto.randomUUID(),
          name: m.name,
          algorithm: m.algorithm,
          weight: m.weight,
          threshold: m.threshold ?? null,
        }))
      : [newRow()],
  );

  const patchRow = (id: string, patch: Partial<MetricRow>) =>
    setRows(rs => rs.map(r => (r._id === id ? { ...r, ...patch } : r)));
  const removeRow = (id: string) =>
    setRows(rs => (rs.length > 1 ? rs.filter(r => r._id !== id) : rs));

  const weightSum = rows.reduce((s, r) => s + (r.weight || 0), 0);
  const canSubmit =
    !loading &&
    (isEdit || !!name.trim()) &&
    rows.length > 0 &&
    rows.every(r => r.name.trim() && r.algorithm) &&
    weightSum > 0;

  const buildMetrics = (): MetricSpec[] =>
    rows.map(r => ({
      name: r.name.trim(),
      algorithm: r.algorithm,
      weight: r.weight,
      threshold: r.threshold,
    }));

  const handleSubmit = () => {
    if (!canSubmit) return;
    if (isEdit) {
      const payload: UpdateEvalTemplateRequest = {
        description: description.trim() || undefined,
        metrics: buildMetrics(),
        judge_provider: judgeProvider.trim() || undefined,
      };
      onSubmit(payload);
    } else {
      const payload: CreateEvalTemplateRequest = {
        name: name.trim(),
        description: description.trim() || undefined,
        metrics: buildMetrics(),
        judge_provider: judgeProvider.trim() || undefined,
      };
      onSubmit(payload);
    }
  };

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="lg">
        <ModalHeader>
          <ModalTitle>{isEdit ? '编辑评分模板' : '新建评分模板'}</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>
                模板名 <span className="text-rose-500">*</span>
                {isEdit && (
                  <span className="ml-1 text-[11px] text-stone-400">
                    · 不可改（保存即 version+1）
                  </span>
                )}
              </Label>
              <Input
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="RAG 质量基线"
                disabled={isEdit}
                maxLength={64}
              />
            </div>
            <div className="space-y-1.5">
              <Label>评判模型 / Provider</Label>
              <Input
                value={judgeProvider}
                onChange={e => setJudgeProvider(e.target.value)}
                placeholder="可选 · RAGAS 类算子用的 LLM"
                maxLength={64}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>描述</Label>
            <Input
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="可选"
              maxLength={500}
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>
                评分指标 <span className="text-rose-500">*</span>
                <span className="ml-1 text-[11px] text-stone-400">
                  · 多指标按权重加权；权重和 {weightSum.toFixed(2)}
                </span>
              </Label>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setRows(rs => [...rs, newRow()])}
              >
                <Plus className="mr-1 h-3.5 w-3.5" /> 加指标
              </Button>
            </div>
            <div className="space-y-2">
              <div className="grid grid-cols-[1.4fr_1.6fr_0.7fr_0.8fr_auto] gap-2 px-1 text-[10.5px] text-stone-400">
                <span>指标名</span>
                <span>算子</span>
                <span>权重</span>
                <span>阈值</span>
                <span />
              </div>
              {rows.map(r => (
                <div
                  key={r._id}
                  className="grid grid-cols-[1.4fr_1.6fr_0.7fr_0.8fr_auto] items-center gap-2"
                >
                  <Input
                    value={r.name}
                    onChange={e => patchRow(r._id, { name: e.target.value })}
                    placeholder="忠实度"
                    className="text-[12px]"
                  />
                  <Select
                    value={r.algorithm}
                    onValueChange={v => patchRow(r._id, { algorithm: v })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ALGO_OPTIONS.map(o => (
                        <SelectItem key={o.value} value={o.value}>
                          {o.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Input
                    type="number"
                    step={0.1}
                    min={0}
                    max={1}
                    value={r.weight}
                    onChange={e =>
                      patchRow(r._id, {
                        weight: parseFloat(e.target.value) || 0,
                      })
                    }
                  />
                  <Input
                    type="number"
                    step={0.05}
                    min={0}
                    max={1}
                    value={r.threshold ?? ''}
                    placeholder="—"
                    onChange={e => {
                      const v = e.target.value;
                      patchRow(r._id, {
                        threshold: v === '' ? null : parseFloat(v),
                      });
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => removeRow(r._id)}
                    disabled={rows.length <= 1}
                    className="rounded p-1.5 text-stone-400 transition hover:bg-rose-50 hover:text-rose-600 disabled:opacity-30"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button
            variant="primary"
            disabled={!canSubmit}
            onClick={handleSubmit}
          >
            {loading ? '保存中…' : isEdit ? '保存' : '创建'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

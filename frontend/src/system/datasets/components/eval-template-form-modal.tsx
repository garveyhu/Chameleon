/** 评分方案 创建/编辑 Modal —— RAGAS 多指标加权配置。
 *  评分方案 = 一组「RAGAS 算子 + 权重 + 阈值」的可复用打分配置，用于评估 RAG 质量。
 *  编辑时方案名锁定：后端 update 自动 version+1，老 EvalJob 引用 freeze 不动。 */

import { Info, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';

import { ModelPicker } from '@/core/components/common/model-picker';
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
import { cn } from '@/core/lib/cn';
import type {
  CreateEvalTemplateRequest,
  EvalTemplateItem,
  MetricSpec,
  UpdateEvalTemplateRequest,
} from '@/system/datasets/types/eval-template';

/** 后端实际注册的 4 个 RAGAS 算子（chameleon.engine.eval.algorithms）。
 *  key 必须与后端 register_algorithm 完全一致，否则打分时「算子未注册」直接失败。 */
type Need = 'judge' | 'context' | 'reference';
interface AlgoMeta {
  key: string;
  zh: string;
  desc: string;
  needs: Need[];
}
const NEED_LABEL: Record<Need, string> = {
  judge: '评判模型',
  context: '检索上下文',
  reference: '参考答案',
};
const RAGAS_ALGOS: AlgoMeta[] = [
  {
    key: 'ragas_faithfulness',
    zh: '忠实度',
    desc: '答案中每句话是否都能被检索到的上下文支持——分低说明模型在「编」(幻觉)。',
    needs: ['judge', 'context'],
  },
  {
    key: 'ragas_answer_relevance',
    zh: '答案相关性',
    desc: '答案是否对题——LLM 从答案反推问题再比相似度，分低说明答非所问 / 跑题。',
    needs: ['judge'],
  },
  {
    key: 'ragas_context_precision',
    zh: '上下文精确率',
    desc: '检索回来的每个片段对回答是否有用——衡量检索「准不准」(噪声多不多)。',
    needs: ['judge', 'context'],
  },
  {
    key: 'ragas_context_recall',
    zh: '上下文召回率',
    desc: '参考答案里的每句是否都被检索上下文覆盖——衡量检索「全不全」(漏没漏)。',
    needs: ['judge', 'context', 'reference'],
  },
];
const ALGO_BY_KEY = new Map(RAGAS_ALGOS.map(a => [a.key, a]));
const ZH_DEFAULTS = new Set(RAGAS_ALGOS.map(a => a.zh));

interface MetricRow {
  _id: string;
  name: string;
  algorithm: string;
  weight: number;
  threshold: number | null;
}

const newRow = (algo: AlgoMeta = RAGAS_ALGOS[0]): MetricRow => ({
  _id: crypto.randomUUID(),
  name: algo.zh,
  algorithm: algo.key,
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
  const [name, setName] = useState(() => initial?.name ?? '');
  const [description, setDescription] = useState(() => initial?.description ?? '');
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

  // 切算子时：指标名若为空 / 仍是某个算子默认中文名，则同步成新算子的中文名（保留用户自定义名）。
  const changeAlgo = (id: string, key: string) => {
    const algo = ALGO_BY_KEY.get(key);
    setRows(rs =>
      rs.map(r => {
        if (r._id !== id) return r;
        const keepName = r.name.trim() && !ZH_DEFAULTS.has(r.name.trim());
        return { ...r, algorithm: key, name: keepName ? r.name : (algo?.zh ?? r.name) };
      }),
    );
  };

  const usedKeys = new Set(rows.map(r => r.algorithm));
  const addAlgo = (algo: AlgoMeta) => setRows(rs => [...rs, newRow(algo)]);

  const weightSum = rows.reduce((s, r) => s + (r.weight || 0), 0);
  const canSubmit =
    !loading &&
    (isEdit || !!name.trim()) &&
    rows.length > 0 &&
    rows.every(r => r.name.trim() && ALGO_BY_KEY.has(r.algorithm)) &&
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
    const base = {
      description: description.trim() || undefined,
      metrics: buildMetrics(),
      judge_provider: judgeProvider.trim() || undefined,
    };
    onSubmit(isEdit ? base : { name: name.trim(), ...base });
  };

  // 哪些 needs 在本方案出现 → 顶部前置条件提示
  const allNeeds = new Set<Need>();
  rows.forEach(r => ALGO_BY_KEY.get(r.algorithm)?.needs.forEach(n => allNeeds.add(n)));

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="lg">
        <ModalHeader>
          <ModalTitle>{isEdit ? '编辑评分方案' : '新建评分方案'}</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div className="flex gap-2 rounded-lg bg-sky-50/70 px-3 py-2 text-[11.5px] leading-snug text-sky-800">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sky-500" />
            <div>
              评分方案 = 一组 RAGAS 指标的加权打分，用来评估 RAG 应用的质量（忠实度 /
              相关性 / 检索精度等）。建好后在「新建评估」「定时任务」里选它打分。
              <span className="text-sky-600">
                每个指标都由 LLM 评判模型逐条打 0–1 分，按权重加权成总分。
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>
                方案名 <span className="text-rose-500">*</span>
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
              <Label>
                评判模型 <span className="text-rose-500">*</span>
              </Label>
              <ModelPicker
                value={judgeProvider}
                onChange={setJudgeProvider}
                placeholder="不指定 · 用系统默认模型"
                width={232}
              />
              <p className="text-[10.5px] leading-tight text-stone-400">
                RAGAS 指标全靠这个大模型逐条评判，留空用系统默认；建议选能力强的模型。
              </p>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>描述</Label>
            <Input
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="可选，如：忠实度 / 答案相关性 / 检索精度 加权评分"
              maxLength={500}
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>
                评分指标 <span className="text-rose-500">*</span>
                <span className="ml-1 text-[11px] text-stone-400">
                  · 按权重加权（权重和 {weightSum.toFixed(2)}，会自动归一）
                </span>
              </Label>
            </div>

            {/* 快速添加：只有 4 个 RAGAS 算子，直接给可点的胶囊，未加的可一键加 */}
            <div className="flex flex-wrap gap-1.5">
              {RAGAS_ALGOS.map(a => (
                <button
                  key={a.key}
                  type="button"
                  disabled={usedKeys.has(a.key)}
                  onClick={() => addAlgo(a)}
                  title={a.desc}
                  className={cn(
                    'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] transition',
                    usedKeys.has(a.key)
                      ? 'cursor-default border-stone-200 bg-stone-100 text-stone-400'
                      : 'border-primary-200 text-primary-700 hover:bg-primary-50',
                  )}
                >
                  <Plus className="h-3 w-3" /> {a.zh}
                </button>
              ))}
            </div>

            <div className="space-y-2">
              <div className="grid grid-cols-[1.3fr_1.7fr_0.7fr_0.8fr_auto] gap-2 px-1 text-[10.5px] text-stone-400">
                <span>指标名（显示用）</span>
                <span>RAGAS 算子</span>
                <span title="该指标占总分的权重，多指标按比例归一">权重 ⓘ</span>
                <span title="低于此分视为未达标（可空，仅用于标红提示）">阈值 ⓘ</span>
                <span />
              </div>
              {rows.map(r => {
                const algo = ALGO_BY_KEY.get(r.algorithm);
                return (
                  <div key={r._id} className="space-y-1">
                    <div className="grid grid-cols-[1.3fr_1.7fr_0.7fr_0.8fr_auto] items-center gap-2">
                      <Input
                        value={r.name}
                        onChange={e => patchRow(r._id, { name: e.target.value })}
                        placeholder="忠实度"
                        className="text-[12px]"
                      />
                      <Select
                        value={r.algorithm}
                        onValueChange={v => changeAlgo(r._id, v)}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="选 RAGAS 算子…" />
                        </SelectTrigger>
                        <SelectContent>
                          {RAGAS_ALGOS.map(a => (
                            <SelectItem key={a.key} value={a.key}>
                              {a.zh}
                              <span className="ml-1.5 font-mono text-[10px] text-stone-400">
                                {a.key}
                              </span>
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
                          patchRow(r._id, { weight: parseFloat(e.target.value) || 0 })
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
                          patchRow(r._id, { threshold: v === '' ? null : parseFloat(v) });
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
                    {algo && (
                      <div className="flex flex-wrap items-center gap-1.5 px-1 text-[10.5px] text-stone-400">
                        <span>{algo.desc}</span>
                        {algo.needs.map(n => (
                          <span
                            key={n}
                            className="rounded bg-amber-50 px-1 py-0.5 text-[9.5px] text-amber-700"
                          >
                            需{NEED_LABEL[n]}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {allNeeds.size > 0 && (
              <div className="rounded-md bg-amber-50/70 px-2.5 py-1.5 text-[10.5px] leading-snug text-amber-700">
                前置条件：本方案用到的指标需要——
                {allNeeds.has('judge') && '① 配好评判模型；'}
                {allNeeds.has('context') &&
                  '② 被测对象（智能体）回答时要返回检索到的上下文；'}
                {allNeeds.has('reference') && '③ 数据集样本要填「理想回答」作为参考。'}
                缺失项该指标会打 0 分。
              </div>
            )}
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button variant="primary" disabled={!canSubmit} onClick={handleSubmit}>
            {loading ? '保存中…' : isEdit ? '保存' : '创建'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

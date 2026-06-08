/** 数据集「能力维度」配置：增删维度行 + AI 建议。样本归类 + 对比雷达的轴据此而来。 */

import { useMutation } from '@tanstack/react-query';
import { Plus, Sparkles, X } from 'lucide-react';

import { Input } from '@/core/components/ui/input';
import { NeonLoader } from '@/core/components/ui/neon-loader';
import { toast } from '@/core/lib/toast';
import { datasetApi } from '@/system/datasets/services/dataset';
import type { CategoryDef } from '@/system/datasets/types/dataset';

interface Props {
  value: CategoryDef[];
  onChange: (v: CategoryDef[]) => void;
  /** AI 建议用：当前表单的名/描述/系统提示词 */
  name: string;
  description?: string;
  systemPrompt?: string;
}

export const DatasetCategoriesField = ({
  value,
  onChange,
  name,
  description,
  systemPrompt,
}: Props) => {
  const suggestMut = useMutation({
    mutationFn: () =>
      datasetApi.suggestCategories({
        name: name.trim() || '评测数据集',
        description: description?.trim() || undefined,
        system_prompt: systemPrompt?.trim() || undefined,
      }),
    onSuccess: cats => {
      if (cats.length) {
        onChange(cats);
        toast.success(`AI 建议了 ${cats.length} 个维度`);
      } else {
        toast.info('AI 没给出维度，请手动添加');
      }
    },
    onError: () => toast.error('AI 建议失败，请重试'),
  });

  const addRow = () => {
    const keys = new Set(value.map(c => c.key));
    let i = value.length + 1;
    let key = `cat${i}`;
    while (keys.has(key)) key = `cat${++i}`;
    onChange([...value, { key, label: '', description: '' }]);
  };
  const patch = (idx: number, p: Partial<CategoryDef>) =>
    onChange(value.map((c, i) => (i === idx ? { ...c, ...p } : c)));
  const remove = (idx: number) =>
    onChange(value.filter((_, i) => i !== idx));

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-[11.5px] text-stone-600">
          能力维度（可选，用于样本归类 + 对比雷达）
        </label>
        <button
          type="button"
          onClick={() => suggestMut.mutate()}
          disabled={suggestMut.isPending}
          title="根据名称/描述/系统提示词，让 AI 提一组维度"
          className="inline-flex items-center gap-1 rounded-md border border-violet-200 bg-white px-2 py-0.5 text-[11px] font-medium text-violet-700 transition hover:border-violet-300 disabled:opacity-60"
        >
          {suggestMut.isPending ? (
            <NeonLoader size="xs" />
          ) : (
            <Sparkles className="h-3 w-3" />
          )}
          AI 建议
        </button>
      </div>

      {value.length === 0 ? (
        <p className="text-[10.5px] leading-snug text-stone-400">
          未配置维度时，运行对比页不显示「能力雷达」。手动添加或点「AI 建议」。
        </p>
      ) : (
        <div className="space-y-1.5">
          {value.map((c, idx) => (
            <div key={c.key} className="flex items-center gap-1.5">
              <Input
                value={c.label}
                onChange={e => patch(idx, { label: e.target.value })}
                placeholder="维度名（如 多表连接）"
                className="!h-7 w-32 shrink-0 text-[12px]"
              />
              <Input
                value={c.description ?? ''}
                onChange={e => patch(idx, { description: e.target.value })}
                placeholder="说明（可选，帮 AI 归类更准）"
                className="!h-7 flex-1 text-[12px]"
              />
              <button
                type="button"
                onClick={() => remove(idx)}
                className="shrink-0 rounded p-1 text-stone-400 transition hover:text-rose-600"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={addRow}
        className="inline-flex items-center gap-1 text-[11px] text-stone-500 transition hover:text-stone-700"
      >
        <Plus className="h-3 w-3" /> 添加维度
      </button>
    </div>
  );
};

/** 样本编辑抽屉 —— 输入 / 预期输出 / 元数据 三段全字段编辑（专业 JSON 编辑器）。
 *  取代旧的「只能改预期」标注弹窗。 */

import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';

import { Button } from '@/core/components/ui/button';
import { JsonEditor } from '@/core/components/ui/json-editor';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import { toast } from '@/core/lib/toast';
import { datasetApi } from '@/system/datasets/services/dataset';
import type {
  CategoryDef,
  DatasetItemRow,
  UpdateItemRequest,
} from '@/system/datasets/types/dataset';

// Radix Select 不允许空串 value，用哨兵代表「未分类」
const NONE = '__none__';

interface Props {
  item: DatasetItemRow;
  /** 数据集配置的能力维度（供「能力维度」下拉选项） */
  categories?: CategoryDef[];
  onClose: () => void;
  onSaved: () => void;
}

const toText = (v: unknown): string =>
  v == null ? '' : JSON.stringify(v, null, 2);

type Parsed = { ok: boolean; value: Record<string, unknown> | null };

const parseField = (t: string): Parsed => {
  const s = t.trim();
  if (!s) return { ok: true, value: null };
  try {
    const j: unknown = JSON.parse(s);
    return {
      ok: true,
      value:
        j !== null && typeof j === 'object' && !Array.isArray(j)
          ? (j as Record<string, unknown>)
          : { value: j },
    };
  } catch {
    return { ok: false, value: null };
  }
};

export const DatasetItemEditorDrawer = ({
  item,
  categories,
  onClose,
  onSaved,
}: Props) => {
  const [input, setInput] = useState(() => toText(item.input_payload));
  const [expected, setExpected] = useState(() => toText(item.expected_output));
  const [meta, setMeta] = useState(() => toText(item.meta));
  const [note, setNote] = useState(() => item.note ?? '');
  const [category, setCategory] = useState(() => item.category ?? '');

  const mut = useMutation({
    mutationFn: (req: UpdateItemRequest) => datasetApi.updateItem(item.id, req),
    onSuccess: () => {
      toast.success('已保存');
      onSaved();
    },
    onError: (e: unknown) =>
      toast.error((e as { message?: string })?.message || '保存失败'),
  });

  const save = () => {
    const i = parseField(input);
    const e = parseField(expected);
    const m = parseField(meta);
    if (!i.ok || !e.ok || !m.ok) {
      toast.error('有字段 JSON 格式错误，请先修正');
      return;
    }
    if (i.value == null) {
      toast.error('输入不能为空');
      return;
    }
    mut.mutate({
      input_payload: i.value,
      expected_output: e.value,
      meta: m.value,
      note: note.trim(),
      category: category || '',
    });
  };

  return (
    <Sheet open onOpenChange={o => !o && onClose()}>
      <SheetContent width="w-[640px]">
        <SheetHeader>
          <SheetTitle className="text-[15px]">编辑样本</SheetTitle>
          <p className="text-[11.5px] text-stone-500">
            输入变量 / 预期输出 / 元数据 —— 专业 JSON 编辑器，实时校验 + 一键格式化
          </p>
        </SheetHeader>
        <SheetBody className="space-y-4">
          <div>
            <div className="mb-1 text-[11.5px] text-stone-600">
              输入 <span className="text-rose-500">*</span>
              <span className="ml-1 text-[10.5px] text-stone-400">
                样本的问题 / 变量，必填
              </span>
            </div>
            <JsonEditor label="输入" value={input} onChange={setInput} />
          </div>
          <div>
            <div className="mb-1 text-[11.5px] text-stone-600">
              预期输出
              <span className="ml-1 text-[10.5px] text-stone-400">
                金标准答案，留空表示无预期
              </span>
            </div>
            <JsonEditor
              label="预期输出"
              value={expected}
              onChange={setExpected}
            />
          </div>
          <div>
            <div className="mb-1 text-[11.5px] text-stone-600">
              元数据 meta
              <span className="ml-1 text-[10.5px] text-stone-400">
                标签 / 难度 / 来源等，可选
              </span>
            </div>
            <JsonEditor
              label="meta"
              value={meta}
              onChange={setMeta}
              minHeight="80px"
            />
          </div>
          <div>
            <div className="mb-1 text-[11.5px] text-stone-600">
              备注
              <span className="ml-1 text-[10.5px] text-stone-400">
                描述这条样本用于评测什么，可选
              </span>
            </div>
            <textarea
              value={note}
              onChange={e => setNote(e.target.value)}
              rows={2}
              placeholder="如：考察多表 JOIN / 嵌套子查询 / HAVING 过滤等"
              className="w-full rounded-md border border-stone-200 bg-white px-2.5 py-1.5 text-[12.5px] leading-snug text-stone-800 outline-none transition placeholder:text-stone-300 focus:border-blue-300 focus:ring-1 focus:ring-blue-100"
            />
          </div>
          {categories && categories.length > 0 && (
            <div>
              <div className="mb-1 text-[11.5px] text-stone-600">
                能力维度
                <span className="ml-1 text-[10.5px] text-stone-400">
                  归到一个维度（对比雷达据此分轴），可选
                </span>
              </div>
              <Select
                value={category || NONE}
                onValueChange={v => setCategory(v === NONE ? '' : v)}
              >
                <SelectTrigger className="h-9 text-[12.5px]">
                  <SelectValue placeholder="未分类" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>未分类</SelectItem>
                  {categories.map(c => (
                    <SelectItem key={c.key} value={c.key}>
                      {c.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </SheetBody>
        <div className="flex justify-end gap-2 border-t border-stone-100 px-4 py-3">
          <Button variant="ghost" size="sm" onClick={onClose}>
            取消
          </Button>
          <Button size="sm" disabled={mut.isPending} onClick={save}>
            {mut.isPending ? '保存中…' : '保存'}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
};

/** KB 元数据字段管理（KB-P5）
 *
 * 列出 KB 下的元数据字段定义（key/label/类型/选项）+ 添加 + 删除。
 * 文档值存 Document.meta（按 key）；检索可按字段值过滤（P5-2）。
 */
import { useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Tag, Trash2 } from 'lucide-react';

import { SectionCard } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
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
import { confirm } from '@/core/lib/confirm';
import { get, post } from '@/core/lib/request';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';

type FieldType = 'string' | 'number' | 'select' | 'time';

interface MetadataField {
  id: EntityId;
  kb_id: EntityId;
  key: string;
  label: string;
  field_type: FieldType;
  options: string[] | null;
}

const TYPE_LABEL: Record<FieldType, string> = {
  string: '文本',
  number: '数值',
  select: '枚举',
  time: '时间',
};

const TYPE_OPTIONS: { value: FieldType; label: string }[] = [
  { value: 'string', label: '文本（自由输入）' },
  { value: 'number', label: '数值' },
  { value: 'select', label: '枚举（候选值）' },
  { value: 'time', label: '时间 / 日期' },
];

interface Props {
  kbId: EntityId;
}

export const MetadataFieldsTab = ({ kbId }: Props) => {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);

  const listQ = useQuery({
    queryKey: ['kb-metadata-fields', kbId],
    queryFn: () => get<MetadataField[]>(`/v1/admin/kbs/${kbId}/metadata-fields`),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ['kb-metadata-fields', kbId] });

  const deleteMut = useMutation({
    mutationFn: (fieldId: EntityId) =>
      post(`/v1/admin/kbs/${kbId}/metadata-fields/${fieldId}/delete`, {}),
    onSuccess: () => {
      toast.success('字段已删除');
      invalidate();
    },
    onError: e => toast.error(`删除失败：${(e as Error).message}`),
  });

  const fields = listQ.data ?? [];

  const onDelete = async (f: MetadataField) => {
    if (
      await confirm({
        title: `删除字段「${f.label}」？`,
        description: '仅删除字段定义，文档已写入的值保留在 meta 中。',
        danger: true,
        confirmText: '删除',
      })
    ) {
      deleteMut.mutate(f.id);
    }
  };

  return (
    <SectionCard>
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-[14px] font-medium text-stone-900">元数据字段</h3>
          <p className="mt-0.5 text-[11.5px] text-stone-500">
            为 KB 定义结构化字段；文档在元数据里按 key 填值，检索可按字段过滤。
          </p>
        </div>
        <Button size="sm" onClick={() => setOpen(true)}>
          <Plus className="mr-1 h-3.5 w-3.5" />
          添加字段
        </Button>
      </div>

      {listQ.isLoading ? (
        <div className="py-10 text-center text-sm text-stone-400">加载中…</div>
      ) : fields.length === 0 ? (
        <div className="py-12 text-center text-sm text-stone-400">
          还没有字段，点「添加字段」开始定义
        </div>
      ) : (
        <div className="divide-y divide-stone-100 overflow-hidden rounded-lg border border-stone-200/60">
          {fields.map(f => (
            <div
              key={f.id}
              className="group flex items-center justify-between px-3 py-2.5 hover:bg-stone-50/60"
            >
              <div className="flex items-center gap-3">
                <Tag className="h-3.5 w-3.5 text-stone-400" />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-medium text-stone-900">{f.label}</span>
                    <code className="rounded bg-stone-100 px-1.5 py-0.5 font-mono text-[10.5px] text-stone-500">
                      {f.key}
                    </code>
                    <Badge variant="outline" className="text-[10px]">
                      {TYPE_LABEL[f.field_type]}
                    </Badge>
                  </div>
                  {f.field_type === 'select' && f.options && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {f.options.map(o => (
                        <span
                          key={o}
                          className="rounded bg-stone-100 px-1.5 py-0.5 text-[10px] text-stone-500"
                        >
                          {o}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              <button
                type="button"
                title="删除"
                onClick={() => onDelete(f)}
                className="rounded p-1 text-stone-400 opacity-0 transition group-hover:opacity-100 hover:bg-rose-50 hover:text-rose-600"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      <AddFieldModal
        kbId={kbId}
        open={open}
        onClose={() => setOpen(false)}
        onSaved={() => {
          setOpen(false);
          invalidate();
        }}
      />
    </SectionCard>
  );
};

const AddFieldModal = ({
  kbId,
  open,
  onClose,
  onSaved,
}: {
  kbId: EntityId;
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}) => {
  const [key, setKey] = useState('');
  const [label, setLabel] = useState('');
  const [fieldType, setFieldType] = useState<FieldType>('string');
  const [optionsText, setOptionsText] = useState('');

  const reset = () => {
    setKey('');
    setLabel('');
    setFieldType('string');
    setOptionsText('');
  };

  const createMut = useMutation({
    mutationFn: () => {
      const options =
        fieldType === 'select'
          ? optionsText
              .split(/[,，\n]/)
              .map(s => s.trim())
              .filter(Boolean)
          : undefined;
      return post(`/v1/admin/kbs/${kbId}/metadata-fields`, {
        key: key.trim(),
        label: label.trim(),
        field_type: fieldType,
        options,
      });
    },
    onSuccess: () => {
      toast.success('字段已添加');
      reset();
      onSaved();
    },
    onError: e => toast.error(`添加失败：${(e as Error).message}`),
  });

  const selectInvalid = fieldType === 'select' && !optionsText.split(/[,，\n]/).some(s => s.trim());
  const disabled = !key.trim() || !label.trim() || selectInvalid || createMut.isPending;

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="md">
        <ModalHeader>
          <ModalTitle>添加元数据字段</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-3">
          <div>
            <Label>字段名（label）</Label>
            <Input
              value={label}
              onChange={e => setLabel(e.target.value)}
              placeholder="如：分类 / 作者 / 发布日期"
              className="mt-1 h-8 text-[12.5px]"
            />
          </div>
          <div>
            <Label>key（写入 meta 的键）</Label>
            <Input
              value={key}
              onChange={e => setKey(e.target.value)}
              placeholder="如：category（字母开头，仅字母/数字/下划线）"
              className="mt-1 h-8 font-mono text-[12.5px]"
            />
          </div>
          <div>
            <Label>类型</Label>
            <Select value={fieldType} onValueChange={v => setFieldType(v as FieldType)}>
              <SelectTrigger className="mt-1 h-8 text-[12.5px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TYPE_OPTIONS.map(o => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {fieldType === 'select' && (
            <div>
              <Label>候选值（逗号或换行分隔）</Label>
              <Input
                value={optionsText}
                onChange={e => setOptionsText(e.target.value)}
                placeholder="如：财务, 技术, 市场"
                className="mt-1 h-8 text-[12.5px]"
              />
            </div>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button onClick={() => createMut.mutate()} disabled={disabled}>
            添加
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

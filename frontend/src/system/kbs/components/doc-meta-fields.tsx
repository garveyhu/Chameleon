/** 文档元数据编辑：按 KB 定义的字段渲染类型化输入 + 其余自由键值
 *
 * 闭环：在「元数据」tab 定义字段 → 这里每篇文档按字段填值 → 召回测试按字段过滤。
 * 定义字段走类型化输入（文本/数字/下拉/日期）写入 Document.meta[key]；
 * 未被定义覆盖的键走自由 MetadataEditor（不丢已有的临时元数据）。
 */

import { useQuery } from '@tanstack/react-query';

import { Input } from '@/core/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { get } from '@/core/lib/request';
import type { EntityId } from '@/core/types/api';
import { MetadataEditor } from '@/system/kbs/components/metadata-editor';
import type { KbMetadataField } from '@/system/kbs/types/kb';

interface Props {
  kbId: EntityId;
  value: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}

export const DocMetaFields = ({ kbId, value, onChange }: Props) => {
  const fieldsQ = useQuery({
    queryKey: ['kb-metadata-fields', kbId],
    queryFn: () => get<KbMetadataField[]>(`/v1/admin/kbs/${kbId}/metadata-fields`),
  });
  const fields = fieldsQ.data ?? [];
  const definedKeys = new Set(fields.map(f => f.key));

  const setField = (key: string, v: unknown) => {
    const next = { ...value };
    if (v === '' || v == null) delete next[key];
    else next[key] = v;
    onChange(next);
  };

  // 未被定义字段覆盖的键 → 自由编辑器
  const extra = Object.fromEntries(
    Object.entries(value).filter(([k]) => !definedKeys.has(k)),
  );
  const onExtraChange = (nextExtra: Record<string, unknown>) => {
    const defined = Object.fromEntries(
      Object.entries(value).filter(([k]) => definedKeys.has(k)),
    );
    onChange({ ...defined, ...nextExtra });
  };

  return (
    <div className="space-y-2.5">
      {fields.length > 0 && (
        <div className="space-y-2 rounded-md border border-stone-200/70 bg-stone-50/40 p-2.5">
          {fields.map(f => (
            <div key={String(f.id)} className="flex items-center gap-2">
              <label className="w-20 shrink-0 truncate text-[11.5px] text-stone-600">
                {f.label}
              </label>
              <FieldInput field={f} value={value[f.key]} onChange={v => setField(f.key, v)} />
            </div>
          ))}
        </div>
      )}
      <div>
        {fields.length > 0 && (
          <div className="mb-1 text-[10.5px] text-stone-400">其他元数据（自由键值）</div>
        )}
        <MetadataEditor value={extra} onChange={onExtraChange} />
      </div>
    </div>
  );
};

const FieldInput = ({
  field,
  value,
  onChange,
}: {
  field: KbMetadataField;
  value: unknown;
  onChange: (v: unknown) => void;
}) => {
  const str = value == null ? '' : String(value);

  if (field.field_type === 'select' && field.options) {
    return (
      <Select
        value={str || '__none__'}
        onValueChange={v => onChange(v === '__none__' ? '' : v)}
      >
        <SelectTrigger className="h-7 flex-1 text-[12px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__none__">不填</SelectItem>
          {field.options.map(o => (
            <SelectItem key={o} value={o}>
              {o}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }

  if (field.field_type === 'number') {
    return (
      <Input
        type="number"
        value={str}
        onChange={e => onChange(e.target.value === '' ? '' : Number(e.target.value))}
        placeholder={`填写 ${field.label}`}
        className="h-7 flex-1 text-[12px]"
      />
    );
  }

  if (field.field_type === 'time') {
    return (
      <Input
        type="date"
        value={str}
        onChange={e => onChange(e.target.value)}
        className="h-7 flex-1 text-[12px]"
      />
    );
  }

  return (
    <Input
      value={str}
      onChange={e => onChange(e.target.value)}
      placeholder={`填写 ${field.label}`}
      className="h-7 flex-1 text-[12px]"
    />
  );
};

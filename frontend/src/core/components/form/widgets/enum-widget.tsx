/** Enum widget —— Select 单选；支持 schema.enumNames 自定义显示 */

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import type { WidgetProps } from '@/core/components/form/types';

export const EnumWidget: React.FC<WidgetProps<string | number | boolean>> = ({
  schema,
  value,
  onChange,
  name,
  disabled,
}) => {
  const options = Array.isArray(schema.enum) ? schema.enum : [];
  // 自定义显示名（按 index 对应 enum 值）
  const names =
    Array.isArray(schema.enumNames) && schema.enumNames.length === options.length
      ? (schema.enumNames as (string | number | boolean)[])
      : null;

  const displayValue = value === undefined || value === null ? '' : String(value);

  return (
    <Select
      value={displayValue}
      onValueChange={v => {
        if (v === '') {
          onChange(undefined);
          return;
        }
        const idx = options.findIndex(o => String(o) === v);
        onChange(idx >= 0 ? options[idx] : undefined);
      }}
      disabled={disabled}
    >
      <SelectTrigger id={name}>
        <SelectValue placeholder="选择…" />
      </SelectTrigger>
      <SelectContent>
        {options.map((opt, i) => (
          <SelectItem key={String(opt)} value={String(opt)}>
            {String(names ? names[i] : opt)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
};

/** String widget —— 根据 format 选 input / textarea / password */

import { Input } from '@/core/components/ui/input';
import { Textarea } from '@/core/components/ui/textarea';
import { getPlaceholder, type WidgetProps } from '@/core/components/form/types';

export const StringWidget: React.FC<WidgetProps<string>> = ({
  schema,
  value,
  onChange,
  name,
  disabled,
}) => {
  const format = schema.format;
  const placeholder = getPlaceholder(schema);
  const v = value ?? '';

  const handle = (raw: string) => {
    // 空串与 undefined 区分：空串视为"清空"，让上层可决定是否走默认值
    onChange(raw === '' ? undefined : raw);
  };

  if (format === 'textarea') {
    return (
      <Textarea
        id={name}
        value={v}
        onChange={e => handle(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        rows={3}
        maxLength={schema.maxLength}
      />
    );
  }

  const htmlType =
    format === 'password'
      ? 'password'
      : format === 'email'
        ? 'email'
        : format === 'uri' || format === 'url'
          ? 'url'
          : 'text';

  return (
    <Input
      id={name}
      type={htmlType}
      value={v}
      onChange={e => handle(e.target.value)}
      placeholder={placeholder}
      disabled={disabled}
      maxLength={schema.maxLength}
      minLength={schema.minLength}
    />
  );
};

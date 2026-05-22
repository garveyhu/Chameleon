/** Number / Integer widget */

import { Input } from '@/core/components/ui/input';
import { getPlaceholder, type WidgetProps } from '@/core/components/form/types';

export const NumberWidget: React.FC<WidgetProps<number>> = ({
  schema,
  value,
  onChange,
  name,
  disabled,
}) => {
  const placeholder = getPlaceholder(schema);
  const isInteger = schema.type === 'integer';
  const step = isInteger ? 1 : 'any';

  // value 为 undefined 时 input 显示空，让用户可清空
  const display = typeof value === 'number' ? String(value) : '';

  const handle = (raw: string) => {
    if (raw === '') {
      onChange(undefined);
      return;
    }
    const n = isInteger ? parseInt(raw, 10) : parseFloat(raw);
    if (Number.isFinite(n)) {
      onChange(n);
    }
  };

  return (
    <Input
      id={name}
      type="number"
      value={display}
      onChange={e => handle(e.target.value)}
      placeholder={placeholder}
      disabled={disabled}
      min={schema.minimum}
      max={schema.maximum}
      step={step}
    />
  );
};

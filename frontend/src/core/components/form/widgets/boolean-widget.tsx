/** Boolean widget —— Switch toggle */

import { Switch } from '@/core/components/ui/switch';
import type { WidgetProps } from '@/core/components/form/types';

export const BooleanWidget: React.FC<WidgetProps<boolean>> = ({
  value,
  onChange,
  name,
  disabled,
}) => (
  <Switch
    id={name}
    checked={value === true}
    onCheckedChange={v => onChange(v)}
    disabled={disabled}
  />
);

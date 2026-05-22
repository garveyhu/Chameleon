/** Object widget —— 递归渲染嵌套对象 */

import { SchemaField } from '@/core/components/form/schema-field';
import type { WidgetProps } from '@/core/components/form/types';

export const ObjectWidget: React.FC<WidgetProps<Record<string, unknown>>> = ({
  schema,
  value,
  onChange,
  depth = 0,
  disabled,
}) => {
  const props = schema.properties ?? {};
  const required = new Set(schema.required ?? []);

  const obj = value ?? {};

  const handleChild = (key: string, next: unknown) => {
    const merged = { ...obj, [key]: next };
    // undefined 值剔除（与 string-widget 的"空→undefined"约定一致）
    if (next === undefined) {
      delete (merged as Record<string, unknown>)[key];
    }
    onChange(Object.keys(merged).length ? merged : undefined);
  };

  const entries = Object.entries(props);
  if (entries.length === 0) {
    return (
      <div className="text-[11px] italic text-stone-400">
        （此对象无字段定义）
      </div>
    );
  }

  // depth >= 1 时套一个浅卡片，便于视觉层级
  const containerCls =
    depth === 0
      ? 'space-y-3'
      : 'space-y-3 rounded-md border border-stone-200/70 bg-stone-50/40 p-3';

  return (
    <div className={containerCls}>
      {entries.map(([key, propSchema]) => (
        <SchemaField
          key={key}
          name={key}
          schema={propSchema}
          value={obj[key]}
          onChange={next => handleChild(key, next)}
          required={required.has(key)}
          depth={depth + 1}
          disabled={disabled}
        />
      ))}
    </div>
  );
};

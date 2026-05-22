/** Array widget —— 单类型 items，支持 add / remove / 拖序后续加 */

import { Plus, Trash2 } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { SchemaField } from '@/core/components/form/schema-field';
import type { JsonSchema, WidgetProps } from '@/core/components/form/types';

export const ArrayWidget: React.FC<WidgetProps<unknown[]>> = ({
  schema,
  value,
  onChange,
  depth = 0,
  disabled,
}) => {
  const items: JsonSchema = schema.items ?? { type: 'string' };
  const list = Array.isArray(value) ? value : [];

  const update = (next: unknown[]) => {
    onChange(next.length ? next : undefined);
  };

  const setAt = (i: number, v: unknown) => {
    const next = [...list];
    next[i] = v;
    update(next);
  };

  const remove = (i: number) => {
    const next = list.filter((_, idx) => idx !== i);
    update(next);
  };

  const add = () => {
    // 推一个 undefined 占位，让 widget 内部空态显示
    update([...list, undefined]);
  };

  return (
    <div className="space-y-2">
      {list.map((item, i) => (
        <div
          key={i}
          className="flex items-start gap-2 rounded-md border border-stone-200/70 bg-paper p-2"
        >
          <div className="flex-1">
            <SchemaField
              name={`[${i}]`}
              schema={items}
              value={item}
              onChange={next => setAt(i, next)}
              depth={depth + 1}
              disabled={disabled}
            />
          </div>
          <button
            type="button"
            onClick={() => remove(i)}
            disabled={disabled}
            className="mt-0.5 rounded p-1 text-stone-400 transition hover:bg-stone-100 hover:text-rose-600 disabled:opacity-50"
            title="删除该项"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={add} disabled={disabled}>
        <Plus className="h-3.5 w-3.5" /> 添加一项
      </Button>
    </div>
  );
};

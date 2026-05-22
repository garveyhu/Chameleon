/** JSONSchemaForm —— 后端 JSON Schema → React 表单
 *
 * 设计目标：
 * - 受控：外部传入 value + onChange；组件不持有 form state
 * - 后端是 truth source（Pydantic 已校验），前端只做 UX 级提示
 * - 支持的 schema 子集见 [[json-schema-form.test.tsx]] 测试与组件 README
 *
 * 用法：
 *   const [value, setValue] = useState<unknown>(undefined)
 *   <JSONSchemaForm schema={schema} value={value} onChange={setValue} />
 */

import { useMemo } from 'react';

import { ObjectWidget } from '@/core/components/form/widgets/object-widget';
import { SchemaField } from '@/core/components/form/schema-field';
import type { JsonSchema } from '@/core/services/schema';

interface JSONSchemaFormProps {
  /** 顶层 schema —— 通常是 type=object，properties 是字段定义 */
  schema: JsonSchema;
  /** 当前值；顶层应为 dict（如果 schema.type=object）或单一原始值 */
  value: unknown;
  /** 值变更回调 */
  onChange: (next: unknown) => void;
  /** 整体禁用 */
  disabled?: boolean;
  /** 顶层 className 覆盖 */
  className?: string;
}

export const JSONSchemaForm: React.FC<JSONSchemaFormProps> = ({
  schema,
  value,
  onChange,
  disabled,
  className,
}) => {
  const isObject = schema.type === 'object';
  const isEmpty = useMemo(
    () => isObject && Object.keys(schema.properties ?? {}).length === 0,
    [isObject, schema.properties],
  );

  if (isEmpty) {
    return (
      <div className="rounded-md border border-stone-200/70 bg-stone-50/30 px-3 py-2 text-[12px] text-stone-500">
        Schema 内没有字段定义。
      </div>
    );
  }

  return (
    <div className={className ?? 'space-y-3'}>
      {isObject ? (
        // 顶层 object 不套外层 label，直接展开 properties
        <ObjectWidget
          name=""
          schema={schema}
          value={value as Record<string, unknown> | undefined}
          onChange={next => onChange(next)}
          depth={0}
          disabled={disabled}
        />
      ) : (
        <SchemaField
          name=""
          schema={schema}
          value={value}
          onChange={onChange}
          disabled={disabled}
        />
      )}
    </div>
  );
};

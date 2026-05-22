/** SchemaField —— 单字段渲染入口
 *
 * 根据 schema.type 派发到对应 widget；包装 label / description / error 等公共结构。
 * 不直接处理嵌套 —— object/array widget 自己再递归回 SchemaField。
 */

import { Label } from '@/core/components/ui/label';
import { BooleanWidget } from '@/core/components/form/widgets/boolean-widget';
import { EnumWidget } from '@/core/components/form/widgets/enum-widget';
import { NumberWidget } from '@/core/components/form/widgets/number-widget';
import { StringWidget } from '@/core/components/form/widgets/string-widget';
import { ArrayWidget } from '@/core/components/form/widgets/array-widget';
import { ObjectWidget } from '@/core/components/form/widgets/object-widget';
import {
  getFieldTitle,
  resolveWidgetKind,
  unwrapOptional,
  type WidgetProps,
} from '@/core/components/form/types';

export const SchemaField: React.FC<WidgetProps> = props => {
  // 把 Optional 解包成真实 schema，title/description 透传
  const schema = unwrapOptional(props.schema);
  const kind = resolveWidgetKind(schema);
  const title = getFieldTitle(schema, props.name);
  const description = schema.description;
  const required = !!props.required;

  // Boolean / Switch 类型 label 与 widget 同行；其他在 widget 之上
  const labelInline = kind === 'boolean';

  const widget = renderWidget(kind, { ...props, schema });

  return (
    <div
      className={
        labelInline
          ? 'flex items-center justify-between gap-3 py-1'
          : 'space-y-1'
      }
    >
      <div className={labelInline ? 'space-y-0.5' : 'flex items-baseline gap-1.5'}>
        <Label htmlFor={props.name} className="text-[12.5px] text-stone-700">
          {title}
          {required ? <span className="ml-0.5 text-rose-500">*</span> : null}
        </Label>
        {description && !labelInline ? (
          <span className="text-[11px] text-stone-400">· {description}</span>
        ) : null}
        {description && labelInline ? (
          <div className="text-[11px] text-stone-400">{description}</div>
        ) : null}
      </div>
      <div className={labelInline ? 'shrink-0' : ''}>{widget}</div>
      {props.error ? (
        <div className="text-[11px] text-rose-500">{props.error}</div>
      ) : null}
    </div>
  );
};

function renderWidget(kind: string, props: WidgetProps): React.ReactNode {
  switch (kind) {
    case 'string':
      return <StringWidget {...(props as WidgetProps<string>)} />;
    case 'number':
    case 'integer':
      return <NumberWidget {...(props as WidgetProps<number>)} />;
    case 'boolean':
      return <BooleanWidget {...(props as WidgetProps<boolean>)} />;
    case 'enum':
      return (
        <EnumWidget {...(props as WidgetProps<string | number | boolean>)} />
      );
    case 'object':
      return <ObjectWidget {...(props as WidgetProps<Record<string, unknown>>)} />;
    case 'array':
      return <ArrayWidget {...(props as WidgetProps<unknown[]>)} />;
    default:
      return (
        <div className="rounded border border-amber-200 bg-amber-50/40 px-2 py-1 text-[11px] text-amber-700">
          不支持的 schema 类型：{props.schema.type || '(unknown)'}
        </div>
      );
  }
}

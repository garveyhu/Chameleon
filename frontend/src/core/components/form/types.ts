/** JSONSchemaForm 内部共用类型 */

import type { JsonSchema } from '@/core/services/schema';

export type { JsonSchema };

/** 通用 Widget Props —— 所有内置 widget 接受相同形状 */
export interface WidgetProps<T = unknown> {
  /** 该字段的 schema 节点 */
  schema: JsonSchema;
  /** 当前值（受控） */
  value: T | undefined;
  /** 值变更回调 */
  onChange: (next: T | undefined) => void;
  /** 字段在父对象里的 key 名 —— 用作 label 兜底和 a11y */
  name: string;
  /** 父对象的 required 列表里是否含本字段 */
  required?: boolean;
  /** 字段层级（嵌套对象用），从 0 起 */
  depth?: number;
  /** 禁用整个字段 */
  disabled?: boolean;
  /** 校验错误（外部传入，覆盖内置最小校验） */
  error?: string | null;
}

/** 推断 schema 主类型 —— 简单优先级，不支持 oneOf/anyOf 多类型选择 */
export type WidgetKind =
  | 'string'
  | 'number'
  | 'integer'
  | 'boolean'
  | 'enum'
  | 'object'
  | 'array'
  | 'unknown';

export function resolveWidgetKind(schema: JsonSchema): WidgetKind {
  // 处理 anyOf 形如 [ {type: T}, {type: null} ] 的 Optional
  if (Array.isArray(schema.anyOf)) {
    const non_null = schema.anyOf.find(s => s.type !== 'null');
    if (non_null) {
      return resolveWidgetKind(non_null);
    }
  }
  if (Array.isArray(schema.enum) && schema.enum.length > 0) {
    return 'enum';
  }
  switch (schema.type) {
    case 'string':
      return 'string';
    case 'number':
      return 'number';
    case 'integer':
      return 'integer';
    case 'boolean':
      return 'boolean';
    case 'object':
      return 'object';
    case 'array':
      return 'array';
    default:
      return 'unknown';
  }
}

/** 取 schema 上的展示 title，兜底用 name */
export function getFieldTitle(schema: JsonSchema, name: string): string {
  if (typeof schema.title === 'string' && schema.title) return schema.title;
  return name;
}

/** placeholder 取 schema.placeholder（Pydantic json_schema_extra 注入）兜底 */
export function getPlaceholder(schema: JsonSchema): string | undefined {
  if (typeof schema.placeholder === 'string') return schema.placeholder;
  return undefined;
}

/** 把 Optional anyOf 解包成真实 schema —— 渲染时用真实类型节点 */
export function unwrapOptional(schema: JsonSchema): JsonSchema {
  if (Array.isArray(schema.anyOf)) {
    const non_null = schema.anyOf.find(s => s.type !== 'null');
    if (non_null) {
      // 把外层 title/description 透传进真实节点
      return {
        ...non_null,
        title: schema.title ?? non_null.title,
        description: schema.description ?? non_null.description,
        placeholder: schema.placeholder ?? non_null.placeholder,
      };
    }
  }
  return schema;
}

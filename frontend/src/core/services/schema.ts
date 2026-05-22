/** Schema API —— 拉后端 Pydantic 模型注册过的 JSON Schema
 *
 * 跟 /v1/admin/schemas/* 路由对应。前端动态表单 / Workflow Node 配置 /
 * 插件配置等场景按 name 拉同一份 schema，避免前后端字段定义重复。
 */

import { get } from '@/core/lib/request';

export interface SchemaListItem {
  name: string;
  title: string | null;
  qualified_name: string;
}

/** JSON Schema 是递归结构，前端按需展开；这里只标关键字段，其余照透传 */
export interface JsonSchema {
  type?: string;
  title?: string;
  description?: string;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  enum?: (string | number | boolean)[];
  default?: unknown;
  format?: string;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  items?: JsonSchema;
  $ref?: string;
  $defs?: Record<string, JsonSchema>;
  anyOf?: JsonSchema[];
  // 自定义 UI hint（Pydantic json_schema_extra 透传）
  placeholder?: string;
  // 其余字段照透
  [key: string]: unknown;
}

export const schemaApi = {
  /** 列出已注册 schema name；可按 prefix 过滤 */
  list: (params?: { prefix?: string }) =>
    get<SchemaListItem[]>('/v1/admin/schemas', { params }),

  /** 按 name 取单个 schema dump；inlineRefs=true 把 $defs/$ref 内联便于直接渲染 */
  get: (name: string, opts?: { inlineRefs?: boolean }) =>
    get<JsonSchema>(`/v1/admin/schemas/${encodeURIComponent(name)}`, {
      params: opts?.inlineRefs ? { inline_refs: true } : undefined,
    }),
};

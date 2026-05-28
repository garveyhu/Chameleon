/** API 文档站「端点规约」类型定义
 *
 * 每个 endpoint 是一份**纯数据**配置——文档站 UI 只读这些字段渲染，
 * 新增端点只用在 registry/ 下新加 .ts 文件，不动核心代码。
 */
import type { ReactNode } from 'react';

export type AuthKind =
  | 'bearer-key' //   Authorization: Bearer xxx（API Key）
  | 'admin-jwt' //    管理员 JWT
  | 'session-token' // embed widget 颁的短期 token
  | 'origin-whitelist'; //  仅按 Origin 白名单（无 token）

/** 参数 / 字段规约（path / query / body / response field 通用） */
export interface ParamSpec {
  name: string;
  /** 'string' / 'integer' / 'boolean' / 'object' / 'enum: text|url' 等；自由文本 */
  type: string;
  required?: boolean;
  /** 默认值（已序列化为字面量字符串/数字/布尔/null） */
  default?: string | number | boolean | null;
  desc: string;
  /** 示例值（仅 doc 展示） */
  example?: unknown;
}

export interface ResponseSpec {
  /** HTTP 状态码 */
  code: number;
  /** 标题，缺省 '200 - application/json' */
  name?: string;
  desc?: string;
  /** 响应体示例（JSON-serializable） */
  example?: unknown;
}

/** 端点分组 —— 控制左导航分组结构（i18n 与图标可扩展，先用文本 + 默认图标） */
export interface GroupMeta {
  /** 分组 key，端点 group 字段引用 */
  key: string;
  /** 分组显示名 */
  title: string;
  /** 排序权重（小的靠前） */
  order: number;
}

export interface EndpointSpec {
  /** 全局唯一 id，深链用：?endpoint=invoke */
  id: string;
  /** 归属分组 key（必须在 registry/_groups.ts 注册） */
  group: string;
  /** 端点显示名 */
  title: string;
  method: 'GET' | 'POST';
  /** 完整路径（含 /v1 前缀），path param 用 {name} 占位 */
  path: string;
  /** 一段说明（支持富文本节点） */
  desc: ReactNode;
  auth: AuthKind;
  /** 排序权重（同组内，小的靠前） */
  order?: number;

  pathParams?: ParamSpec[];
  queryParams?: ParamSpec[];
  bodyParams?: ParamSpec[];

  responses: ResponseSpec[];
  /** 完整 cURL 命令字符串（含 {BASE} 占位会被替换为实际 base url） */
  cURL: string;
}

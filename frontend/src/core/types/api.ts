/** 后端统一响应封装（与 backend chameleon-core/api/response.py 对齐） */

/** 后端走雪花 ID（64-bit）。> Number.MAX_SAFE_INTEGER 的 ID 走 JSON 解析时
 *  会被 request.ts 的 transformResponse 包成字符串保精度，所以业务侧
 *  统一用 `EntityId = number | string`。URL 模板字符串与 === 比较均兼容。 */
export type EntityId = number | string;

export interface Result<T> {
  code: number;
  message: string;
  success: boolean;
  data: T;
}

export interface PageResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface PageQuery {
  page?: number;
  page_size?: number;
}

/** 通用 ID 引用对象 */
export interface IdRef {
  id: EntityId;
}

/** 后端统一响应封装（与 backend chameleon-core/api/response.py 对齐） */

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
  id: number;
}

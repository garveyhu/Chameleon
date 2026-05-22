/** 应用级常量 */

/** 本地存储 key：access_token / 用户基础信息 */
export const STORAGE_KEY = {
  ACCESS_TOKEN: 'chameleon:access_token',
  USER: 'chameleon:user',
  LOCALE: 'chameleon:locale',
  PREFERENCES: 'chameleon:preferences',
} as const;

/** Refresh 由 cookie 自动携带，不在前端持久化 */
export const REFRESH_COOKIE_NAME = 'chameleon_refresh';

/** 默认分页 */
export const DEFAULT_PAGE_SIZE = 20;

/** 默认 access_token 过期前自动 refresh 阈值（秒） */
export const REFRESH_THRESHOLD_SECONDS = 60;

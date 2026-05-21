/** axios 请求封装
 *
 * 职责：
 * - 注入 Authorization: Bearer <access_token>
 * - 拦截 401 → 自动 POST /v1/auth/refresh → 重试一次
 * - 解包 Result<T> 外壳，业务层直接拿 data
 * - 错误统一 toast
 */

import axios, {
  type AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios';
import { toast } from 'sonner';

import { STORAGE_KEY } from '@/core/constants/app';
import type { Result } from '@/core/types/api';
import type { TokenPair } from '@/core/types/auth';

const http: AxiosInstance = axios.create({
  baseURL: '/',
  timeout: 30_000,
  withCredentials: true, // refresh_token cookie 需要
});

// ── token 管理（in-memory + localStorage） ─────────────────

let accessToken: string | null =
  localStorage.getItem(STORAGE_KEY.ACCESS_TOKEN) || null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
  if (token) {
    localStorage.setItem(STORAGE_KEY.ACCESS_TOKEN, token);
  } else {
    localStorage.removeItem(STORAGE_KEY.ACCESS_TOKEN);
  }
}

export function getAccessToken(): string | null {
  return accessToken;
}

// ── 401 自动 refresh（含并发去重） ──────────────────────────

let refreshing: Promise<string | null> | null = null;

async function tryRefresh(): Promise<string | null> {
  if (refreshing) return refreshing;
  refreshing = (async () => {
    try {
      const res = await axios.post<Result<TokenPair>>(
        '/v1/auth/refresh',
        {},
        { withCredentials: true },
      );
      const newToken = res.data.data.access_token;
      setAccessToken(newToken);
      return newToken;
    } catch {
      setAccessToken(null);
      return null;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

// ── interceptor ────────────────────────────────────────────

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

http.interceptors.response.use(
  response => response,
  async (error: AxiosError<Result<unknown>>) => {
    const original = error.config as
      | (InternalAxiosRequestConfig & { _retry?: boolean })
      | undefined;
    const status = error.response?.status;
    const body = error.response?.data;

    // access 过期 → refresh + retry 一次
    if (
      status === 401 &&
      original &&
      !original._retry &&
      !original.url?.includes('/v1/auth/login') &&
      !original.url?.includes('/v1/auth/refresh')
    ) {
      original._retry = true;
      const newToken = await tryRefresh();
      if (newToken) {
        original.headers.Authorization = `Bearer ${newToken}`;
        return http.request(original);
      }
      // refresh 失败 → 跳登录
      window.location.href = '/login';
      return Promise.reject(error);
    }

    // 业务错误（4xx / 5xx）统一 toast
    const message =
      body?.message ||
      (typeof body === 'string' ? body : null) ||
      error.message ||
      '请求失败';
    if (status && status >= 400) {
      // 401 已上跳，这里不再 toast 避免双弹
      if (status !== 401) {
        toast.error(message);
      }
    }
    return Promise.reject(error);
  },
);

// ── 业务层接口（解包 Result.data） ─────────────────────────

async function unwrap<T>(promise: Promise<{ data: Result<T> }>): Promise<T> {
  const res = await promise;
  if (!res.data.success && res.data.code !== 0 && res.data.code !== 200) {
    throw new Error(res.data.message);
  }
  return res.data.data;
}

export function get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  return unwrap(http.get<Result<T>>(url, config));
}

export function post<T>(
  url: string,
  data?: unknown,
  config?: AxiosRequestConfig,
): Promise<T> {
  return unwrap(http.post<Result<T>>(url, data, config));
}

export function postForm<T>(
  url: string,
  formData: FormData,
  config?: AxiosRequestConfig,
): Promise<T> {
  return unwrap(
    http.post<Result<T>>(url, formData, {
      ...config,
      headers: { ...(config?.headers || {}), 'Content-Type': 'multipart/form-data' },
    }),
  );
}

/** 拿原始 axios response（用于下载二进制） */
export function getRaw<T = Blob>(
  url: string,
  config?: AxiosRequestConfig,
): Promise<{ data: T; headers: Record<string, string> }> {
  return http
    .get(url, { ...config, responseType: 'blob' })
    .then(r => ({ data: r.data as T, headers: r.headers as Record<string, string> }));
}

export { http };

/** auth API 调用 */

import { get, post } from '@/core/lib/request';
import type {
  ChangePasswordRequest,
  CurrentUserView,
  FirstPasswordRequest,
  LoginRequest,
  TokenPair,
} from '@/core/types/auth';

export const authApi = {
  login: (req: LoginRequest) => post<TokenPair>('/v1/auth/login', req),
  refresh: () => post<TokenPair>('/v1/auth/refresh'),
  logout: () => post<void>('/v1/auth/logout'),
  me: () => get<CurrentUserView>('/v1/auth/me'),
  changePassword: (req: ChangePasswordRequest) =>
    post<void>('/v1/auth/change-password', req),
  firstChangePassword: (req: FirstPasswordRequest) =>
    post<void>('/v1/auth/first-change-password', req),
};

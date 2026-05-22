import type { EntityId } from '@/core/types/api';
import { get, post } from '@/core/lib/request';
import type { PageResult } from '@/core/types/api';
import type {
  CreateUserRequest,
  ResetPasswordRequest,
  UpdateUserRequest,
  UserItem,
} from '@/system/users/types/user';

export const userApi = {
  list: (params?: { page?: number; page_size?: number }) =>
    get<PageResult<UserItem>>('/v1/admin/users', { params }),
  get: (id: EntityId) => get<UserItem>(`/v1/admin/users/${id}`),
  create: (req: CreateUserRequest) => post<UserItem>('/v1/admin/users', req),
  update: (id: EntityId, req: UpdateUserRequest) =>
    post<UserItem>(`/v1/admin/users/${id}/update`, req),
  delete: (id: EntityId) => post<void>(`/v1/admin/users/${id}/delete`),
  resetPassword: (id: EntityId, req: ResetPasswordRequest) =>
    post<void>(`/v1/admin/users/${id}/reset-password`, req),
  grantRole: (id: EntityId, role_code: string) =>
    post<UserItem>(`/v1/admin/users/${id}/roles/grant`, { role_code }),
  revokeRole: (id: EntityId, role_code: string) =>
    post<UserItem>(`/v1/admin/users/${id}/roles/revoke`, { role_code }),
};

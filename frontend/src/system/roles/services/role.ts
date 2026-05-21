import { get, post } from '@/core/lib/request';
import type { PermissionItem, RoleItem } from '@/system/roles/types/role';

export const roleApi = {
  list: () => get<RoleItem[]>('/v1/admin/roles'),
  create: (req: { code: string; name: string; description?: string }) =>
    post<RoleItem>('/v1/admin/roles', req),
  update: (id: number, req: { name?: string; description?: string }) =>
    post<RoleItem>(`/v1/admin/roles/${id}/update`, req),
  delete: (id: number) => post<void>(`/v1/admin/roles/${id}/delete`),
  syncPermissions: (id: number, permission_codes: string[]) =>
    post<RoleItem>(`/v1/admin/roles/${id}/permissions/sync`, { permission_codes }),
};

export const permissionApi = {
  list: (resource?: string) =>
    get<PermissionItem[]>('/v1/admin/permissions', {
      params: resource ? { resource } : undefined,
    }),
};

import { get, post } from '@/core/lib/request';
import type { EntityId } from '@/core/types/api';
import type {
  AddMemberPayload,
  CreateWorkspacePayload,
  MemberItem,
  QuotaItem,
  UpdateMemberRolePayload,
  UpdateQuotaPayload,
  UpdateWorkspacePayload,
  WorkspaceItem,
} from '@/system/workspaces/types/workspace';

export const workspaceApi = {
  list: () => get<WorkspaceItem[]>('/v1/admin/workspaces'),

  get: (id: EntityId) => get<WorkspaceItem>(`/v1/admin/workspaces/${id}`),

  create: (p: CreateWorkspacePayload) =>
    post<WorkspaceItem>('/v1/admin/workspaces', p),

  update: (id: EntityId, p: UpdateWorkspacePayload) =>
    post<WorkspaceItem>(`/v1/admin/workspaces/${id}/update`, p),

  delete: (id: EntityId) =>
    post<null>(`/v1/admin/workspaces/${id}/delete`, {}),

  listMembers: (id: EntityId) =>
    get<MemberItem[]>(`/v1/admin/workspaces/${id}/members`),

  addMember: (id: EntityId, p: AddMemberPayload) =>
    post<MemberItem>(`/v1/admin/workspaces/${id}/members`, p),

  updateMemberRole: (
    id: EntityId,
    membershipId: EntityId,
    p: UpdateMemberRolePayload,
  ) =>
    post<MemberItem>(
      `/v1/admin/workspaces/${id}/members/${membershipId}/update`,
      p,
    ),

  removeMember: (id: EntityId, membershipId: EntityId) =>
    post<null>(
      `/v1/admin/workspaces/${id}/members/${membershipId}/delete`,
      {},
    ),

  getQuota: (id: EntityId) =>
    get<QuotaItem>(`/v1/admin/workspaces/${id}/quota`),

  updateQuota: (id: EntityId, p: UpdateQuotaPayload) =>
    post<QuotaItem>(`/v1/admin/workspaces/${id}/quota/update`, p),
};

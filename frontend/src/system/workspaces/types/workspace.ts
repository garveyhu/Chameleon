import type { EntityId } from '@/core/types/api';

export type WorkspacePlan = 'free' | 'pro' | 'enterprise';
export type MemberRole = 'owner' | 'admin' | 'member' | 'viewer';

export interface WorkspaceItem {
  id: EntityId;
  workspace_key: string;
  name: string;
  plan: WorkspacePlan;
  config: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface CreateWorkspacePayload {
  workspace_key: string;
  name: string;
  plan?: WorkspacePlan;
  config?: Record<string, unknown> | null;
}

export interface UpdateWorkspacePayload {
  name?: string;
  plan?: WorkspacePlan;
  config?: Record<string, unknown> | null;
}

export interface MemberItem {
  id: EntityId;
  user_id: EntityId;
  workspace_id: EntityId;
  team_id: EntityId | null;
  role: MemberRole;
  created_at: string;
  username: string | null;
}

export interface AddMemberPayload {
  user_id: EntityId;
  team_id?: EntityId | null;
  role?: MemberRole;
}

export interface UpdateMemberRolePayload {
  role: MemberRole;
}

export const MEMBER_ROLES: { label: string; value: MemberRole }[] = [
  { label: 'Owner（所有者）', value: 'owner' },
  { label: 'Admin（管理员）', value: 'admin' },
  { label: 'Member（成员）', value: 'member' },
  { label: 'Viewer（只读）', value: 'viewer' },
];

export const PLAN_OPTIONS: { label: string; value: WorkspacePlan }[] = [
  { label: 'Free（社区版）', value: 'free' },
  { label: 'Pro（标准版）', value: 'pro' },
  { label: 'Enterprise（企业版）', value: 'enterprise' },
];

/** 默认 workspace 的固定 id —— 与后端 DEFAULT_WORKSPACE_ID 对齐 */
export const DEFAULT_WORKSPACE_ID = '1';

// ── quota ────────────────────────────────────────────


export interface QuotaItem {
  workspace_id: EntityId;
  token_quota_monthly: number | null;
  token_used_current_month: number;
  request_quota_daily: number | null;
  request_used_today: number;
  reset_at: string;
}

export interface UpdateQuotaPayload {
  token_quota_monthly?: number | null;
  request_quota_daily?: number | null;
  reset_used?: boolean;
}

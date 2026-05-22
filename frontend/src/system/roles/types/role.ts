import type { EntityId } from '@/core/types/api';
export interface RoleItem {
  id: EntityId;
  code: string;
  name: string;
  description: string | null;
  is_system: boolean;
  permission_codes: string[];
}

export interface PermissionItem {
  code: string;
  resource: string;
  action: string;
  description: string | null;
}

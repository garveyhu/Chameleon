export interface RoleItem {
  id: number;
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

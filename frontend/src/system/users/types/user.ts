export interface UserItem {
  id: number;
  username: string;
  email: string | null;
  display_name: string | null;
  status: 'active' | 'disabled';
  locale: string;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at: string;
  role_codes: string[];
}

export interface CreateUserRequest {
  username: string;
  password: string;
  email?: string;
  display_name?: string;
  locale?: string;
  role_codes?: string[];
  must_change_password?: boolean;
}

export interface UpdateUserRequest {
  email?: string;
  display_name?: string;
  locale?: string;
  status?: 'active' | 'disabled';
}

export interface ResetPasswordRequest {
  new_password: string;
  must_change_password?: boolean;
}

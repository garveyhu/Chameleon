/** 鉴权域类型（与后端 chameleon-system/auth 对齐） */

export interface TokenPair {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface CurrentUserView {
  id: number;
  username: string;
  email: string | null;
  display_name: string | null;
  status: 'active' | 'disabled';
  locale: string;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at: string;
  roles: string[];
  permissions: string[];
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface ChangePasswordRequest {
  old_password: string;
  new_password: string;
}

export interface FirstPasswordRequest {
  new_password: string;
}

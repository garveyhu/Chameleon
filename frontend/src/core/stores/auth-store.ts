/** 鉴权全局状态（zustand） */

import { create } from 'zustand';

import { STORAGE_KEY } from '@/core/constants/app';
import { getAccessToken, setAccessToken } from '@/core/lib/request';
import { authApi } from '@/core/services/auth';
import type { CurrentUserView, LoginRequest } from '@/core/types/auth';

interface AuthState {
  user: CurrentUserView | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (req: LoginRequest) => Promise<CurrentUserView>;
  logout: () => Promise<void>;
  fetchMe: () => Promise<CurrentUserView | null>;
  hasPermission: (perm: string) => boolean;
  hasRole: (role: string) => boolean;
}

function _loadCachedUser(): CurrentUserView | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY.USER);
    return raw ? (JSON.parse(raw) as CurrentUserView) : null;
  } catch {
    return null;
  }
}

function _persistUser(u: CurrentUserView | null) {
  if (u) {
    localStorage.setItem(STORAGE_KEY.USER, JSON.stringify(u));
  } else {
    localStorage.removeItem(STORAGE_KEY.USER);
  }
}

function _matchPerm(userPerms: Set<string>, perm: string): boolean {
  if (userPerms.has('*:*') || userPerms.has(perm)) return true;
  const [resource] = perm.split(':');
  return userPerms.has(`${resource}:*`);
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: _loadCachedUser(),
  isAuthenticated: Boolean(getAccessToken() && _loadCachedUser()),
  isLoading: false,

  async login(req) {
    set({ isLoading: true });
    try {
      const pair = await authApi.login(req);
      setAccessToken(pair.access_token);
      const user = await authApi.me();
      _persistUser(user);
      set({ user, isAuthenticated: true, isLoading: false });
      return user;
    } catch (err) {
      set({ isLoading: false });
      throw err;
    }
  },

  async logout() {
    try {
      await authApi.logout();
    } catch {
      // 即使后端失败也清本地
    }
    setAccessToken(null);
    _persistUser(null);
    set({ user: null, isAuthenticated: false });
  },

  async fetchMe() {
    if (!getAccessToken()) return null;
    try {
      const user = await authApi.me();
      _persistUser(user);
      set({ user, isAuthenticated: true });
      return user;
    } catch {
      setAccessToken(null);
      _persistUser(null);
      set({ user: null, isAuthenticated: false });
      return null;
    }
  },

  hasPermission(perm) {
    const u = get().user;
    if (!u) return false;
    return _matchPerm(new Set(u.permissions), perm);
  },

  hasRole(role) {
    const u = get().user;
    if (!u) return false;
    return u.roles.includes(role);
  },
}));

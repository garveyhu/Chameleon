/** 用户偏好（主题色 / 中性色 / 动画）—— Zustand + localStorage
 *
 * 设计：
 * - 8 primary（blue / purple / green / orange / rose / cyan / amber / teal）
 * - 4 neutral（stone / slate / zinc / gray）
 * - 3 animation（disabled / smooth / agile）
 * - mode（light / dark / auto）—— P17 仅占位，dark 实施留 P18
 *
 * 实际生效靠 `<html data-primary data-neutral data-anim data-mode>` 属性，
 * 配合 assets/styles/theme.css 里的 CSS variable overrides。
 */

import { create } from 'zustand';

import { STORAGE_KEY } from '@/core/constants/app';

export type ThemeMode = 'light' | 'dark' | 'auto';

export type PrimaryColor =
  | 'blue'
  | 'purple'
  | 'green'
  | 'orange'
  | 'rose'
  | 'cyan'
  | 'amber'
  | 'teal';

export type NeutralColor = 'stone' | 'slate' | 'zinc' | 'gray';

export type AnimationMode = 'disabled' | 'smooth' | 'agile';

export interface UserPreferences {
  themeMode: ThemeMode;
  primaryColor: PrimaryColor;
  neutralColor: NeutralColor;
  animationMode: AnimationMode;
}

const DEFAULT_PREFERENCES: UserPreferences = {
  themeMode: 'light',
  primaryColor: 'blue',
  neutralColor: 'stone',
  animationMode: 'smooth',
};

interface PreferencesState extends UserPreferences {
  set: <K extends keyof UserPreferences>(
    key: K,
    value: UserPreferences[K],
  ) => void;
  reset: () => void;
}

function _load(): UserPreferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEY.PREFERENCES);
    if (!raw) return DEFAULT_PREFERENCES;
    const parsed = JSON.parse(raw) as Partial<UserPreferences>;
    // 防御性 merge：缺失字段回退默认
    return { ...DEFAULT_PREFERENCES, ...parsed };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

function _persist(p: UserPreferences) {
  try {
    localStorage.setItem(STORAGE_KEY.PREFERENCES, JSON.stringify(p));
  } catch {
    /* localStorage 满 / 无权限：静默 */
  }
}

function _applyToDom(p: UserPreferences) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  root.dataset.primary = p.primaryColor;
  root.dataset.neutral = p.neutralColor;
  root.dataset.anim = p.animationMode;
  root.dataset.mode = p.themeMode;
}

// 首屏立即应用，避免 FOUC
_applyToDom(_load());

export const usePreferencesStore = create<PreferencesState>(set => {
  const initial = _load();
  return {
    ...initial,
    set: (key, value) =>
      set(prev => {
        const next: UserPreferences = { ...prev, [key]: value };
        _persist(next);
        _applyToDom(next);
        return next;
      }),
    reset: () =>
      set(() => {
        _persist(DEFAULT_PREFERENCES);
        _applyToDom(DEFAULT_PREFERENCES);
        return DEFAULT_PREFERENCES;
      }),
  };
});

export const PRIMARY_COLORS: Array<{
  key: PrimaryColor;
  label: string;
  swatch: string;
}> = [
  { key: 'blue', label: '深蓝', swatch: '#3b82f6' },
  { key: 'purple', label: '紫罗兰', swatch: '#8b5cf6' },
  { key: 'green', label: '森林绿', swatch: '#10b981' },
  { key: 'orange', label: '日落橙', swatch: '#f97316' },
  { key: 'rose', label: '玫瑰红', swatch: '#f43f5e' },
  { key: 'cyan', label: '青湖蓝', swatch: '#06b6d4' },
  { key: 'amber', label: '琥珀金', swatch: '#f59e0b' },
  { key: 'teal', label: '碧海绿', swatch: '#14b8a6' },
];

export const NEUTRAL_COLORS: Array<{
  key: NeutralColor;
  label: string;
  swatch: string;
}> = [
  { key: 'stone', label: '暖石灰（暖色）', swatch: '#78716c' },
  { key: 'slate', label: '石板蓝（冷色）', swatch: '#64748b' },
  { key: 'zinc', label: '锌灰（中性）', swatch: '#71717a' },
  { key: 'gray', label: '中性灰', swatch: '#6b7280' },
];

export const ANIMATION_MODES: Array<{
  key: AnimationMode;
  label: string;
  desc: string;
}> = [
  { key: 'disabled', label: '无动画', desc: '禁用所有过渡 / 动画，性能优先' },
  {
    key: 'smooth',
    label: '柔和（默认）',
    desc: '常规过渡，150–250ms，适合大部分场景',
  },
  { key: 'agile', label: '敏捷', desc: '过渡缩短到 80–120ms，操作回弹更快' },
];

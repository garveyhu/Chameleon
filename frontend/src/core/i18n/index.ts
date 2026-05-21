/** i18n 初始化 —— react-i18next
 *
 * 当前接入范围：
 *   - 侧边栏菜单 + 顶栏文案（高频可见）
 *   - 关键页 PageHeader 标题（按需追加）
 *
 * 未做全量接入：业务表单 / 错误提示等仍走中文字面量；
 * 国际化是长期工程，渐进式翻译，先把"骨架"双语化。
 */

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import enUS from './locales/en-US.json';
import zhCN from './locales/zh-CN.json';

const STORAGE_KEY = 'chameleon:lang';

const detect = (): 'zh-CN' | 'en-US' => {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved === 'zh-CN' || saved === 'en-US') return saved;
  return navigator.language.startsWith('zh') ? 'zh-CN' : 'en-US';
};

void i18n.use(initReactI18next).init({
  resources: {
    'zh-CN': { translation: zhCN },
    'en-US': { translation: enUS },
  },
  lng: detect(),
  fallbackLng: 'zh-CN',
  interpolation: { escapeValue: false },
  returnNull: false,
});

export const setLanguage = (lng: 'zh-CN' | 'en-US'): void => {
  void i18n.changeLanguage(lng);
  localStorage.setItem(STORAGE_KEY, lng);
};

export default i18n;

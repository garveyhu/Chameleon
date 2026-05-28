/** widget 入口 ——
 *
 * 业务方使用：
 *   <script src="https://chameleon.example.com/widget.js"
 *           data-embed-key="abc123"
 *           data-api-base="https://chameleon.example.com"
 *           data-external-user-id="biz-user-123"  (可选；external_user_id 模式)
 *           data-jwt-token="eyJhbGci..."          (可选；signed_jwt 模式)
 *           defer></script>
 *
 * 三种身份模式都能 SSR 把值塞到 data-* 上自动初始化；动态场景（登录后异步拿
 * token）才需要走手动 init：
 *   <script>
 *     window.ChameleonWidget.init({
 *       embedKey: 'abc123',
 *       apiBase: 'https://chameleon.example.com',
 *       jwtToken: '...',
 *     });
 *   </script>
 */

import { ChameleonWidget } from './widget';
import type { WidgetOptions } from './types';

interface PublicApi {
  init: (opts: WidgetOptions) => ChameleonWidget;
  version: string;
}

const VERSION = '0.1.0';

declare global {
  interface Window {
    ChameleonWidget?: PublicApi;
  }
}

let instance: ChameleonWidget | null = null;

const init = (opts: WidgetOptions): ChameleonWidget => {
  if (instance) {
    console.warn('[ChameleonWidget] 已初始化过，先销毁旧实例');
    instance.destroy();
  }
  instance = new ChameleonWidget(opts);
  void instance.mount();
  return instance;
};

const publicApi: PublicApi = { init, version: VERSION };

// 暴露到全局
window.ChameleonWidget = publicApi;

// 自动初始化：读 <script data-embed-key> 属性
const auto = () => {
  const script = document.currentScript as HTMLScriptElement | null;
  // currentScript 在 defer/IIFE 下可能为 null，找最后一个匹配的 script
  const fallback = script || findSelfScript();
  if (!fallback) return;
  const embedKey = fallback.getAttribute('data-embed-key');
  if (!embedKey) return;
  const apiBase = fallback.getAttribute('data-api-base') || deriveApiBase(fallback.src);
  const externalUserId = fallback.getAttribute('data-external-user-id') || undefined;
  const jwtToken = fallback.getAttribute('data-jwt-token') || undefined;
  init({ embedKey, apiBase, externalUserId, jwtToken });
};

function findSelfScript(): HTMLScriptElement | null {
  const scripts = Array.from(document.getElementsByTagName('script'));
  for (let i = scripts.length - 1; i >= 0; i--) {
    if (scripts[i].src && scripts[i].src.endsWith('/widget.js')) return scripts[i];
  }
  return null;
}

function deriveApiBase(src: string): string {
  try {
    const u = new URL(src);
    return u.origin;
  } catch {
    return window.location.origin;
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', auto);
} else {
  auto();
}

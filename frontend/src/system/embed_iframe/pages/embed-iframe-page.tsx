/** iframe / 公开对话页 —— /embed/:embedKey
 *
 * 两种用法共用本页：
 *   1. 业务方 <iframe src=".../embed/{key}"> 嵌进自家页面
 *   2. 「对话页打开」在新标签直接作为公开聊天页访问
 *
 * 实现：本页是「壳」—— body 撑满 viewport，动态加载 /widget.js 并以 fullscreen
 * 模式 init。所有视觉（主题色 / header / 消息气泡 / actions / 附件 / followups /
 * 水印）都走 widget 同一套 renderShell + styles.ts，确保 iframe 跟 script
 * widget 「弹出 panel 视觉」完全一致；区别仅是占满父容器、不渲气泡、永远 open。
 *
 * URL 参数透传：?euid=BIZ_USER_ID 或 ?jwt=SIGNED_JWT 用于 external_user_id /
 * signed_jwt 模式，业务方可在自己的 iframe URL 里拼上。
 */
import { useEffect } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';

interface ChameleonWidgetApi {
  init: (opts: {
    embedKey: string;
    apiBase: string;
    externalUserId?: string;
    jwtToken?: string;
    fullscreen?: boolean;
  }) => { destroy: () => void };
  version: string;
}

declare global {
  interface Window {
    ChameleonWidget?: ChameleonWidgetApi;
  }
}

export const EmbedIframePage = () => {
  const { embedKey } = useParams<{ embedKey: string }>();
  const [search] = useSearchParams();
  const externalUserId = search.get('euid') || undefined;
  const jwtToken = search.get('jwt') || undefined;

  useEffect(() => {
    if (!embedKey) return;

    let instance: ReturnType<ChameleonWidgetApi['init']> | null = null;

    const boot = () => {
      const api = window.ChameleonWidget;
      if (!api) return;
      instance = api.init({
        embedKey,
        apiBase: window.location.origin,
        fullscreen: true,
        externalUserId,
        jwtToken,
      });
    };

    if (window.ChameleonWidget) {
      boot();
    } else {
      const s = document.createElement('script');
      s.src = '/widget.js';
      s.async = true;
      s.onload = boot;
      document.body.appendChild(s);
    }

    return () => {
      try {
        instance?.destroy();
      } catch {
        /* 卸载时若 widget 已经清理过则忽略 */
      }
      // script 节点不删 —— 同页再访问时可命中已加载的 window.ChameleonWidget
    };
  }, [embedKey, externalUserId, jwtToken]);

  if (!embedKey) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-stone-50 text-[12.5px] text-stone-500">
        缺少 embed_key
      </div>
    );
  }
  // 壳：什么都不渲；widget 自己挂到 document.body 并占满 viewport
  return <div className="h-screen w-screen bg-white" />;
};

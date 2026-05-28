/** 鉴权说明块 —— 按 AuthKind 渲染对应提示 */
import type { AuthKind } from '@/api-docs/types/endpoint';

const TIPS: Record<AuthKind, { title: string; hint: string; sample: string }> = {
  'bearer-key': {
    title: 'Bearer Token (API Key)',
    hint: '所有请求在 Authorization 头携带本平台颁发的 API Key（app- / agent- / kbs- 等作用域前缀）。',
    sample: 'Authorization: Bearer {API_KEY}',
  },
  'admin-jwt': {
    title: 'Admin JWT',
    hint: '使用平台登录后的 JWT。仅平台后台 / 管理工具使用，外部业务方不要直接调。',
    sample: 'Authorization: Bearer {JWT_TOKEN}',
  },
  'session-token': {
    title: 'Session Token',
    hint: '业务方 widget 先通过 /v1/embed/{embed_key}/session 颁发短期 token，再随每次调用回传。',
    sample: '"session_token": "{TOKEN}"',
  },
  'origin-whitelist': {
    title: 'Origin 白名单',
    hint: '无 token 接口，仅按浏览器 Origin 头比对 embed 配置的白名单放行（公开但受限）。',
    sample: 'Origin: https://your-site.example.com',
  },
};

export const AuthBlock = ({ auth }: { auth: AuthKind }) => {
  const t = TIPS[auth];
  return (
    <div className="mt-4 rounded-lg border border-stone-200 bg-stone-50/70 px-4 py-3">
      <div className="flex items-baseline gap-2">
        <h3 className="text-[12.5px] font-semibold text-stone-800">鉴权</h3>
        <span className="text-[11.5px] text-stone-500">{t.title}</span>
      </div>
      <p className="mt-1.5 text-[12px] leading-relaxed text-stone-600">{t.hint}</p>
      <code className="mt-2 inline-block rounded bg-white px-2 py-1 font-mono text-[11.5px] text-stone-700 ring-1 ring-stone-200">
        {t.sample}
      </code>
    </div>
  );
};

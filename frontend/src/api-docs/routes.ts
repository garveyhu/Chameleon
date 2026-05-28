/** api-docs 独立模块路由
 *
 * 刻意放在 src/api-docs（而非 src/system/*），自成一体、零业务耦合，
 * 将来可整目录拆出去单独部署成「接口文档站」。各服务的接口说明页都收在这里。
 *
 * 路由分两支：
 *  - `/api-docs/*`：独立全屏文档站（不走 MainLayout）；从头像菜单 / 应用 / KB 内嵌入口跳入
 *  - `/api-docs/{kb,agent}/:key`：保留旧的单独应用 / KB mini 文档页（详情页内嵌跳转用，已挂 MainLayout）
 */
import type { ModuleRouteConfig } from '@/core/types/router';

const module: ModuleRouteConfig = {
  moduleId: 'api-docs',
  parentPath: '/',
  order: 30,
  routes: [
    {
      path: '/api-docs/kb/:kbKey',
      lazy: async () => {
        const m = await import('@/api-docs/pages/kb-api-doc-page');
        return { Component: m.KbApiDocPage };
      },
    },
    {
      path: '/api-docs/agent/:agentKey',
      lazy: async () => {
        const m = await import('@/api-docs/pages/agent-api-doc-page');
        return { Component: m.AgentApiDocPage };
      },
    },
  ],
};

export default module;

// ── 独立文档站（不要 MainLayout，全屏占满）─────────────────────────
export const docsStation: ModuleRouteConfig = {
  moduleId: 'api-docs-station',
  parentPath: '__root__',
  order: 31,
  routes: [
    {
      path: '/api-docs',
      lazy: async () => {
        const m = await import('@/api-docs/pages/docs-station-page');
        return { Component: m.DocsStationPage };
      },
    },
  ],
};

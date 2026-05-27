/** api-docs 独立模块路由
 *
 * 刻意放在 src/api-docs（而非 src/system/*），自成一体、零业务耦合，
 * 将来可整目录拆出去单独部署成「接口文档站」。各服务的接口说明页都收在这里。
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

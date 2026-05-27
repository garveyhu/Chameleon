import type { ModuleRouteConfig } from '@/core/types/router';

const loadLedger = async () => {
  const m = await import('@/system/call_logs/pages/session-ledger-page');
  return { Component: m.SessionLedgerPage };
};

const module: ModuleRouteConfig = {
  moduleId: 'call_logs',
  parentPath: '/',
  order: 60,
  routes: [
    // 会话 & 运行账本（主入口）
    { path: '/sessions', lazy: loadLedger },
    // 兼容旧路径：调用日志
    { path: '/call-logs', lazy: loadLedger },
  ],
};

export default module;

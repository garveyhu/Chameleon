# ADR 0009：前端 sage 分层（core/ 共享 + system/ 自包含 + 动态路由发现）

- **Status**: Accepted
- **Date**: 2026-04

## 背景

React 项目常见两种分层：
1. **类型分层** ：`pages/` + `components/` + `services/` + `types/`
2. **功能分层** ：每个业务模块自包含一个目录

Chameleon 有 12 个业务模块（users / roles / apps / providers / models / agents / kbs / call_logs / embed_configs / audit_logs / settings / dashboard / auth），如果用类型分层，每改一个功能要跨 4-5 个目录翻找。

## 决策

采用 **sage 风格**：

```
src/
├── core/                共享基础设施（不含业务知识）
│   ├── lib/             axios / cn / format
│   ├── components/      shadcn ui + common
│   ├── stores/          全局 store（auth）
│   ├── i18n/            i18next
│   ├── router/          路由发现
│   └── types/           跨模块共享类型
├── system/<module>/     业务模块自包含
│   ├── pages/           XxxPage.tsx
│   ├── services/        xxx-api.ts
│   ├── types/           xxx.ts
│   └── routes.ts        export default { moduleId, parentPath, order, routes }
└── router/index.tsx     import.meta.glob('../system/**/routes.ts', { eager: true })
```

新增模块 = 在 `system/` 下新建一个目录 + 写 routes.ts，**不需要改任何外部文件**。

## 理由

- 模块内聚：删一个模块 = `rm -rf system/<module>/`
- 路由免维护：`import.meta.glob` 自动扫
- 权限免维护：sidebar 菜单按 `hasPermission(perm)` 过滤
- parentPath 约定让模块自己说挂哪：`/`（主 layout）/ `__root__`（独立无 layout，如 /login / /embed/:key）

## 后果

- 跨模块复用要走 core/（不允许 module-A import module-B）
- 模块内部禁止再分子模块（深度只允许两层）
- 团队需理解动态路由发现机制（看 `core/router/index.tsx` 一目了然）

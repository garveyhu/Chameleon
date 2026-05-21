# Chameleon Frontend

Chameleon 管理面板前端（占位 —— 待实现）。

## 计划技术栈

| 维度 | 选型 |
|---|---|
| 包管理 | yarn |
| 构建 | Vite |
| 语言 | TypeScript (strict) |
| UI | React 19 |
| 样式 | Tailwind CSS |
| 组件库 | Antd / shadcn 二选一（待定） |
| 状态 | React Context + Zustand（跨页大状态） |
| 数据请求 | TanStack Query + 封装 axios |
| 路由 | React Router v6+ |

## 对接的后端接口

**仅消费** `chameleon-system` 包暴露的 `/v1/admin/*` 接口：
- `/v1/admin/api-keys` — API key 管理
- `/v1/admin/call-logs` — 调用日志
- `/v1/admin/providers/status` — provider 健康监控

业务侧 `/v1/agents/...`、`/v1/knowledge/...` 等（`chameleon-api` 包暴露）不归前端管，是给业务方应用直接调的。

## 状态

未实现 —— 详细方案见 `docs/` 后续补充。

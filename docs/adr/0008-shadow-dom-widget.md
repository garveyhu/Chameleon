# ADR 0008：嵌入式 Widget 用 Shadow DOM + vanilla TS

- **Status**: Accepted
- **Date**: 2026-04

## 背景

需要给业务方提供一行 `<script>` 接入的对话气泡 widget。约束：
- 不能污染业务方网页样式 / 全局 JS
- bundle 越小越好（首屏加载）
- 兼容老业务方页面（jQuery / Bootstrap / Tailwind 都可能存在）

## 决策

- **Shadow DOM** 注入 widget 元素，CSS / DOM 完全隔离
- **vanilla TypeScript** 实现，**不引 React**
- Vite IIFE 构建，单文件 widget.js 自动初始化

## 理由

| 方案 | 优点 | 缺点 |
|---|---|---|
| iframe | 100% 隔离 | 重，无法贴齐业务方页面布局 |
| React 注入 | 开发体验好 | React 17/18/19 共存 + bundle 大（>150KB） |
| **Shadow DOM + vanilla TS** | 隔离 + 轻量 | 手写 DOM 烦琐 |

实测 widget bundle 13 KB / gzip 4.8 KB，远低于 200KB 目标。

## 实现细节

```html
<script src=".../widget.js" data-embed-key="xxx" defer></script>
```

`widget.js` 自动：
1. 找当前 script 标签 → 读 `data-embed-key` / `data-api-base`
2. `new ChameleonWidget({...})` → 在 body 加 `<div>` host
3. `attachShadow({mode: 'open'})` → CSS / DOM 进 shadow tree
4. fetch `/v1/embed/{key}/config` 拉配置 → 渲染气泡 + panel

## 安全

- 消息渲染走 `textContent`，不走 `innerHTML`（XSS-safe）
- session_token 自动续期（过期前 30s 重签）
- Origin 校验由后端做

## 后果

- 无法用 React DevTools 调试 widget（业务方不依赖 React 反而是好事）
- 自己写 DOM diff + event handling，开发量略大

# Chameleon Embed Widget

可嵌入业务方网页的 AI 对话 widget，无依赖、轻量（gzip < 5 KB）、shadow DOM 隔离样式。

## 两种嵌入方式

### 1. JS Widget（右下角浮动气泡）

```html
<script
  src="https://your-chameleon.example.com/widget.js"
  data-embed-key="abc123"
  defer
></script>
```

可选属性：

- `data-embed-key`（必填）：admin 后台创建嵌入配置时生成的 key
- `data-api-base`（可选）：覆盖 API base URL，默认从 script src 推断同 origin

### 2. iframe（嵌入到页面内某个区域）

```html
<iframe
  src="https://your-chameleon.example.com/embed/abc123"
  style="width:400px;height:600px;border:0;border-radius:12px;
         box-shadow:0 8px 24px rgba(0,0,0,.1)"
></iframe>
```

## 后端契约

widget 调用三个公开 endpoint（admin 端在 embed_configs 模块管理）：

| Method | Path | 说明 |
|--------|------|------|
| GET    | `/v1/embed/{embed_key}/config`  | 拉 ui_config + behavior + welcome_message |
| POST   | `/v1/embed/{embed_key}/session` | 颁 session_token（Redis TTL 1h） |
| POST   | `/v1/embed/{embed_key}/invoke`  | `{session_token,input}` → `{answer}` |

服务端会校验 `Origin` header 是否在 `allowed_origins` 白名单中（同源 / 服务端直调时跳过）。

## 编程式 API

```html
<script src=".../widget.js"></script>
<script>
  const widget = window.ChameleonWidget.init({
    embedKey: 'abc123',
    apiBase: 'https://chameleon.example.com',
  });
  // widget.destroy();  // 销毁
</script>
```

## 开发

```bash
cd frontend/embed
yarn install
yarn dev         # 本地预览（http://localhost:5173/?embed_key=xxx&api=http://localhost:7009）
yarn build       # 产出 dist/widget.js，并自动 copy 到 ../public/widget.js
```

`yarn build` 完成后：

- `frontend/embed/dist/widget.js` 独立 IIFE bundle
- `frontend/public/widget.js` 主 frontend 静态资源（被 vite dev/build 同时 serve）

主 frontend `yarn build` 时会把 `public/widget.js` 一起拷到 `dist/`，部署单 origin 即可。

## 设计要点

- **bundle ≤ 200 KB**：vanilla TS，不引 React。当前实际 13 KB / gzip 4.8 KB
- **shadow DOM**：CSS 写在 shadow tree 里，业务方网页样式不会污染 widget
- **XSS 防御**：消息内容用 `textContent` 渲染，不走 innerHTML
- **session 自动续期**：token 过期前 30s 内自动重签
- **同源 Origin 检查**：浏览器自动带 `Origin` header，由后端做白名单校验
- **响应式**：< 480px 屏宽自动撑满

/** 嵌入式 widget 构建配置
 *
 * 产出 IIFE 单文件 widget.js（无依赖，立即执行），由业务方网页 `<script src="...widget.js">` 加载。
 * 不用 UMD：UMD 会尝试 CommonJS exports 副作用，污染业务方页面命名空间。
 */

import path from 'node:path';
import { defineConfig } from 'vite';

export default defineConfig({
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  build: {
    lib: {
      entry: path.resolve(__dirname, 'src/main.ts'),
      name: 'ChameleonWidget',
      formats: ['iife'],
      fileName: () => 'widget.js',
    },
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
    minify: 'esbuild',
    rollupOptions: {
      output: {
        extend: true, // 不覆盖 window.ChameleonWidget（若业务方意外用过同名）
      },
    },
    target: 'es2018', // 现代浏览器友好，体积小
  },
});

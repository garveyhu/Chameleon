import react from '@vitejs/plugin-react';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
    },
  },
  server: {
    port: 6006,
    host: true,
    proxy: {
      // 后端默认 7009（uvicorn ... --port 7009）
      '/v1': { target: 'http://127.0.0.1:7009', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:7009', changeOrigin: true },
      '/ready': { target: 'http://127.0.0.1:7009', changeOrigin: true },
      '/metrics': { target: 'http://127.0.0.1:7009', changeOrigin: true },
    },
  },
  build: {
    sourcemap: true,
    chunkSizeWarningLimit: 1500,
  },
});

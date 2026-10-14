import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
export default defineConfig(({mode}) => ({
  plugins: [react(), {name: 'health', configureServer(server) {
    for (const path of ['/healthz', '/readyz']) server.middlewares.use(path, (_req, res) => {
      res.setHeader('Content-Type', 'application/json'); res.end('{"status":"ok"}');
    });
  }}],
  server: {proxy: {'/api': {target: loadEnv(mode, '.', 'API_PROXY_TARGET').API_PROXY_TARGET ?? 'http://127.0.0.1:8000', changeOrigin: false, timeout: 0, proxyTimeout: 0}}},
  test: {environment: 'jsdom', setupFiles: ['./src/test-setup.ts']},
}));

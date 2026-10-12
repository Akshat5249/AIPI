import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
export default defineConfig({
  plugins: [react(), {name: 'health', configureServer(server) {
    server.middlewares.use('/healthz', (_req, res) => {
      res.setHeader('Content-Type', 'application/json'); res.end('{"status":"ok"}');
    });
  }}],
  test: {environment: 'jsdom', setupFiles: ['./src/test-setup.ts']},
});

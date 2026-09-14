import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Backend target for the dev proxy. Defaults to the Docker Compose service
// name so the frontend container can reach the backend on the compose network.
//
// NOTE: When running this dev server OUTSIDE Docker against a local backend,
// override with VITE_PROXY_TARGET=http://localhost:8002 (the backend's host port).
const proxyTarget = process.env.VITE_PROXY_TARGET || 'http://backend:8000';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Forward API and health requests to the backend so the browser talks
      // to the frontend origin only (no CORS in the common path).
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/health': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './vitest.setup.ts',
    css: true,
  },
});

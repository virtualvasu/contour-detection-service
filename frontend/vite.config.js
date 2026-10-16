import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Same /api path the production nginx setup uses, pointed at a local
    // uvicorn server, so the app needs no extra config in development.
    proxy: {
      '/api': {
        target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      // Browser traces, to a local OpenTelemetry Collector (see observability/).
      '/otlp': {
        target: process.env.OTLP_PROXY_TARGET || 'http://127.0.0.1:4318',
        rewrite: (path) => path.replace(/^\/otlp/, ''),
      },
    },
  },
})

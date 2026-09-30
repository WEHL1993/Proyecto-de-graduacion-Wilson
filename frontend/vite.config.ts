/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// En desarrollo, /api se reenvía al backend; en producción lo resuelve nginx.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000', changeOrigin: true } },
  },
  test: { environment: 'jsdom', globals: true, setupFiles: './src/test/setup.ts' },
})

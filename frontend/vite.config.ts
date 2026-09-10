/// <reference types="vitest/config" />
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  build: {
    // Audits flag public source maps as an information-disclosure finding.
    sourcemap: false,
  },
  server: {
    // Dev-only: forward /api to the backend so the browser stays same-origin.
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: ['src/**/*.{ts,vue}'],
      exclude: ['src/main.ts', 'src/**/*.test.ts'],
      // Threshold is the signal the test-quality audit looks for; raise as
      // the app grows, never lower it to make CI green.
      thresholds: { lines: 60, statements: 60 },
    },
  },
})

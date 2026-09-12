/// <reference types="vitest/config" />
import path from 'node:path'
import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Vite loads .env only from frontend/; the shared .env lives at the repo root,
  // so load it explicitly to wire VITE_API_URL (the dev proxy target) through.
  const env = loadEnv(mode, path.resolve(process.cwd(), '..'))

  return {
    plugins: [vue()],
    build: {
      // Audits flag public source maps as an information-disclosure finding.
      sourcemap: false,
    },
    server: {
      // Dev-only: forward /api to the backend so the browser stays same-origin.
      proxy: {
        '/api': {
          target: env.VITE_API_URL ?? 'http://localhost:8000',
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
        // Only stores and api count toward the threshold: that is where state,
        // the realtime proof and the network boundary live, and where a
        // regression is expensive. Screens are covered by lint and types; adding
        // them would dilute the number (see DECISIONS.md).
        include: ['src/stores/**', 'src/api/**'],
        exclude: ['src/**/*.test.ts'],
        // Threshold is the signal the test-quality audit looks for; raise as
        // the app grows, never lower it to make CI green.
        thresholds: { lines: 80, statements: 80 },
      },
    },
  }
})

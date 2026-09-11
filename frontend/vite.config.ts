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
      // Only stores and api count toward the threshold: that is where state,
      // the realtime proof and the network boundary live, and where a
      // regression is expensive. Screens are covered by lint and types; adding
      // them would dilute the number (see DECISIONS.md).
      include: ['src/stores/**', 'src/api/**'],
      exclude: ['src/**/*.test.ts'],
      // Threshold is the signal the test-quality audit looks for; raise as
      // the app grows, never lower it to make CI green. 75 is what the auth
      // commit's first real suite reaches (stores + api fully exercised).
      thresholds: { lines: 75, statements: 75 },
    },
  },
})

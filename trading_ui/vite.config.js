import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '^/algo/': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/research': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/portfolio': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/llm': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/market': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})

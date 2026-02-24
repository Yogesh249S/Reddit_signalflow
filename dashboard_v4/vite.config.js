import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://django:8080',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://django:8080',
        ws: true,
        changeOrigin: true,
      }
    }
  }
})

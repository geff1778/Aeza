import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
const target = 'http://127.0.0.1:8100'
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 12100,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      '/api': { target, changeOrigin: true },
      '/metrics': { target, changeOrigin: true },
      '/health': { target, changeOrigin: true },
    },
  },
})

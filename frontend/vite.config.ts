import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  root: resolve(__dirname, 'src'),
  server: {
    port: 4200,
    proxy: {
      '/api': {
        target: 'http://localhost:8765',
        changeOrigin: true,
        secure: false,
        ws: true,
        timeout: 30000
      },
      '/ws': {
        target: 'http://localhost:8765',
        ws: true,
        changeOrigin: true,
        secure: false,
        timeout: 30000
      },
      '/news_reports': {
        target: 'http://localhost:8765',
        changeOrigin: true,
        secure: false,
        timeout: 30000
      },
      '/reports': {
        target: 'http://localhost:8765',
        changeOrigin: true,
        secure: false,
        timeout: 30000
      }
    }
  },
  build: {
    outDir: resolve(__dirname, 'dist'),
    emptyOutDir: true
  }
});

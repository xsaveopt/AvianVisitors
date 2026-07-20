import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

const apiTarget = process.env.AV_API_TARGET ?? 'http://127.0.0.1:8099';

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index: fileURLToPath(new URL('./index.html', import.meta.url)),
        public: fileURLToPath(new URL('./public.html', import.meta.url)),
      },
    },
  },
  server: {
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
      '/stream': { target: apiTarget, changeOrigin: true },
    },
  },
});

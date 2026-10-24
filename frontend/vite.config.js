import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/report': 'http://127.0.0.1:8000',
      '/figures': 'http://127.0.0.1:8000',
    },
  },
  build: {
    target: 'es2020',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: { three: ['three'], gsap: ['gsap'] },
      },
    },
  },
});

import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { webcrypto as nodeCrypto } from 'crypto';

if (typeof globalThis.crypto === 'undefined' || typeof globalThis.crypto.getRandomValues !== 'function') {
  // Node <18 未内置 Web Crypto，使用 crypto.webcrypto 填充
  globalThis.crypto = nodeCrypto as unknown as Crypto;
}

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE || 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/ws': {
        target: process.env.VITE_API_BASE?.replace('http', 'ws') || 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
});

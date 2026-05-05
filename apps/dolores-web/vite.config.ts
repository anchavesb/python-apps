import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  base: '/app/',
  server: {
    proxy: {
      '/v1': {
        target: 'http://localhost:8000',
        ws: true,
      },
      // Ensure VAD assets are served as static files, not falling back to index.html
      '/app/vad': {
        target: 'http://localhost:8080',
        rewrite: (path) => path.replace(/^\/app\/vad/, '/vad'),
      }
    },
  },
});

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
    },
  },
});

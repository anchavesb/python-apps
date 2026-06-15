const CACHE_NAME = 'dolores-v2';
const STATIC_ASSETS = [
  '/app/',
  '/app/index.html',
  '/app/manifest.json',
  '/app/icon-192.svg',
  '/app/icon-512.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Don't cache API, WebSocket, or VAD/binary assets (prevents Safari ONNX/WASM crash from poisoned cache entries)
  if (
    url.pathname.startsWith('/v1') ||
    event.request.method !== 'GET' ||
    url.pathname.startsWith('/app/vad/') ||
    /\.(onnx|wasm|mjs)$/.test(url.pathname)
  ) {
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      // Network-first for HTML, cache-first for assets
      if (event.request.headers.get('accept')?.includes('text/html')) {
        return fetch(event.request)
          .then((response) => {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
            return response;
          })
          .catch(() => cached);
      }

      return cached || fetch(event.request).then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        return response;
      });
    })
  );
});

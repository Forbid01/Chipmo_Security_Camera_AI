const CACHE_NAME = 'chipmo-v3';
const STATIC_ASSETS = ['/favicon.svg'];

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
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Never cache API, auth, or SPA navigations. Hash-busted /assets/ come
  // straight from the network too — serving a stale bundle after a Railway
  // redeploy is what produced the 404 spam.
  const isApi = url.pathname.startsWith('/api/') || url.pathname === '/token';
  const isHashedAsset = url.pathname.startsWith('/assets/');
  const isNavigation = req.mode === 'navigate' || req.destination === 'document';

  if (isApi || isHashedAsset || isNavigation) {
    event.respondWith(fetch(req));
    return;
  }

  event.respondWith(
    caches.match(req).then((cached) => cached || fetch(req))
  );
});

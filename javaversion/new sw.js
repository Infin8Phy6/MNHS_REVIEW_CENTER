const CACHE_NAME = 'reviewer-v23'; // Increment this when you update files


// Cache only static assets. Do NOT cache navigations/auth pages.
const ASSETS = [
  // Avoid caching CSS to prevent stale UI rendering issues.
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/manifest.json'
];

// Large questions payload is cached separately so it never interferes with HTML/navigation.
const QUESTIONS_URL = '/questions.json';
const QUESTIONS_CACHE_NAME = 'reviewer-questions-v1'; // bump when questions.json changes
const ALLOWED_CACHES = [CACHE_NAME, QUESTIONS_CACHE_NAME];


self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(ASSETS))
      .catch((err) => {
        // Don't fail install if some assets are unavailable.
        console.warn('SW install: some assets failed to cache', err);
      })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => !ALLOWED_CACHES.includes(k)).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Network-first for cached static assets.
// BYPASS SW cache for auth/OTP/payment endpoints so those are ALWAYS fresh.
self.addEventListener('fetch', (e) => {
  try {
    const url = new URL(e.request.url);

    const bypassPaths = [
      '/signup',
      '/login',
      '/verify_signup',
      '/verify_login',
      '/create-order',
      '/capture-order',
      '/payment-success'
    ];

    if (bypassPaths.includes(url.pathname)) {
      // Bypass SW and also never fall back to cache.
      e.respondWith(fetch(e.request));
      return;
    }

    // Only handle GET requests
    if (e.request.method !== 'GET') return;

    // Cache questions.json separately (large payload). Use cache-first so it feels instant.
    if (url.pathname === QUESTIONS_URL) {
      e.respondWith(
        caches.open(QUESTIONS_CACHE_NAME).then((cache) => {
          return cache.match(e.request).then((cached) => {
            if (cached) {
              // Background refresh (stays unnoticeable).

              fetch(e.request)
                .then((res) => {
                  if (res && res.ok) cache.put(e.request, res.clone());
                })
                .catch(() => {});
              return cached;
            }
            // Nothing cached yet -> fetch, cache, return.
            return fetch(e.request)
              .then((res) => {
                if (res && res.ok) cache.put(e.request, res.clone());
                return res;
              });
          });
        })
      );
      return;
    }

    // Only SW-handle *static assets*. Everything else (login/signup/quiz HTML, etc.) must bypass.
        const isStaticAsset = ASSETS.some(a => url.pathname === a || url.pathname.startsWith(a));
    if (!isStaticAsset) {
      e.respondWith(fetch(e.request));
      return;
    }

    // For cached static assets, use network-first and update cache.
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          if (res && res.ok) {
            // Clone immediately so we never risk reusing a consumed body.
            const resToCache = res.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(e.request, resToCache));
          }
          return res;
        })
        .catch(() => caches.match(e.request))
    );
  } catch (err) {
    console.error('SW fetch handler error:', err);
  }
});


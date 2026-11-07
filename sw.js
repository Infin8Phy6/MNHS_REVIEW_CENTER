// MNHS REVIEW CENTER - offline service worker
// - Precaches the app shell so pages open without internet
// - Stale-while-revalidate for question sets (/api/questions/...)
// - Network-first for page navigations, falls back to cached copy when offline
const CACHE_NAME = 'reviewhub-v26';

const APP_SHELL = [
    '/home',
    '/games',
    '/game/',
    '/games/jumbled/',
    '/games/whoswho/',
    '/games/elemental-table/',
    '/games/elemental-table/static/etg.css',
    '/games/elemental-table/static/etg.js',
    '/games/elemental-table/static/etg_export.js',
    '/games/crossword/',
    '/games/crossword/static/crossword.css',
    '/games/crossword/static/crossword.js',
    '/games/crossword/static/cw_export.js',
    '/games/quantum-architect/',
    '/games/quantum-architect/play',
    '/games/quantum-architect/api/engine',
    '/games/quantum-architect/static/css/app.css',
    '/games/quantum-architect/static/js/game.js',
    '/quiz_setup',
    '/quiz',
    '/signup',
    '/login',
    '/reset_password',
    '/static/style.css',
    '/static/export.js',
    '/static/auth.js',
    '/static/push-reminders.js',
    '/static/manifest.json',
    '/static/icon-192.png',
    '/static/icon-512.png',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) =>
            Promise.allSettled(APP_SHELL.map((url) => cache.add(url)))
        ).then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        // Cache Storage is shared by the whole origin, and the three games run
        // inside this app with their own caches. Only reviewhub-* is ours to
        // clear — deleting theirs is what left a game page with nothing to show.
        caches.keys().then((keys) =>
            Promise.all(keys.filter((k) => k !== CACHE_NAME && k.startsWith('reviewhub-')).map((k) => caches.delete(k)))
        ).then(() => caches.open(CACHE_NAME))
        // Then drop anything that belongs to one signed-in person. A school
        // tablet is shared, and the next student must not be able to open the
        // previous user's profile, results, admin rows or reset link offline.
        .then((cache) => cache.keys().then((requests) =>
            Promise.all(requests
                .filter((req) => isPrivate(new URL(req.url).pathname))
                .map((req) => cache.delete(req))))
        ).then(() => self.clients.claim())
    );
});

const PRIVATE_PATTERNS = [
    /^\/admin/,
    /^\/staff\/home/,
    /^\/staff\/pdf-studio/,
    /^\/profile/,
    /^\/my-results/,
    /^\/resources/,
    /^\/materials/,
    /^\/reset_password\/.+$/,
    /^\/logout/,
    /^\/games\/jumbled\/result\//,
    /^\/games\/elemental-table\/play\//,
    /^\/game\/worksheet/,
    /^\/games\/elemental-table\/worksheet/,
    /^\/games\/jumbled\/worksheet/,
    /^\/games\/quantum-architect\/worksheets/,                      // staff studio: papers, exports, keys
];

function isPrivate(pathname) {
    return PRIVATE_PATTERNS.some((re) => re.test(pathname));
}

function cacheKeyFor(url) {
    // The /quiz shell is identical for every level/subject/topic combination,
    // so all query variants share one cache entry.
    if (url.pathname === '/quiz') return url.pathname;
    return url.pathname + url.search;
}

self.addEventListener('fetch', (event) => {
    const request = event.request;
    if (request.method !== 'GET') return;

    const url = new URL(request.url);
    if (url.origin !== self.location.origin) return;

    // Question sets, and the tables Quantum Architect's board reads its rules and
    // wording from, are the same public JSON for every visitor: served from cache
    // immediately and refreshed in the background.
    if (url.pathname.startsWith('/api/questions/') ||
        url.pathname.startsWith('/games/quantum-architect/api/')) {
        event.respondWith(
            caches.open(CACHE_NAME).then(async (cache) => {
                const cached = await cache.match(request);
                const network = fetch(request).then((response) => {
                    if (response.ok) cache.put(request, response.clone());
                    return response;
                }).catch(() => null);

                if (cached) return cached;
                const fresh = await network;
                if (fresh) return fresh;
                return new Response(JSON.stringify({ error: 'offline' }), {
                    status: 503,
                    headers: { 'Content-Type': 'application/json' },
                });
            })
        );
        return;
    }

    // Static assets: network-first, cache only as the offline fallback. The
    // school tablets are shared, and serving the cached copy first pinned an
    // old game script on every device until the cache name changed - students
    // then played yesterday's broken board. A mounted game keeps its scripts
    // under its own prefix, so any /static/ path is treated here.
    if (url.pathname.indexOf('/static/') !== -1) {
        event.respondWith(
            fetch(request).then((response) => {
                if (response.ok) {
                    caches.open(CACHE_NAME).then((cache) => cache.put(request, response.clone()));
                }
                return response;
            }).catch(async () => {
                const cache = await caches.open(CACHE_NAME);
                const cached = await cache.match(request);
                return cached || Response.error();
            })
        );
        return;
    }

    // Page navigations: network-first, cached copy when offline.
    if (request.mode === 'navigate') {
        event.respondWith(
            (async () => {
                const cache = await caches.open(CACHE_NAME);
                const privatePage = isPrivate(url.pathname);
                try {
                    const response = await fetch(request);
                    // A page that shows one person's own data is never kept on a
                    // shared device, offline or not.
                    if (response.ok && !privatePage) cache.put(cacheKeyFor(url), response.clone());
                    return response;
                } catch (err) {
                    const cached = privatePage ? null :
                        (await cache.match(cacheKeyFor(url))) ||
                        (await cache.match(url.pathname));
                    if (cached) return cached;
                    if (url.pathname === '/' || url.pathname === '/home') {
                        const home = await cache.match('/home');
                        if (home) return home;
                    }
                    // Only the home page may stand in for itself. Serving /home
                    // for a game or results link looks like the app bounced the
                    // student back out of what they just opened.
                    const safe = url.pathname.replace(/[&<>"']/g, '');
                    return new Response(
                        '<h1>You are offline</h1><p>' + safe + ' was not saved on this device yet. ' +
                        'Open the app once while online and it will be kept for offline use.</p>' +
                        '<p><a href="/home">Go to the home page</a></p>',
                        { status: 503, headers: { 'Content-Type': 'text/html' } }
                    );
                }
            })()
        );
    }
});

// --- Schedule reminders (Web Push) ---
// The server sends {title, body, url} minutes before a class or as a morning
// digest; the device shows it in its own notification tray even with every
// tab closed. Tapping opens (or focuses) the app on the right landing page.
self.addEventListener('push', (event) => {
    let data = {};
    try { data = event.data ? event.data.json() : {}; } catch (err) { data = {}; }
    event.waitUntil(
        self.registration.showNotification(data.title || 'MNHS REVIEW CENTER', {
            body: data.body || 'Open the review center app to see the details.',
            icon: '/static/icon-192.png',
            badge: '/static/icon-192.png',
            tag: data.tag || 'mnhs-reminder',
            data: { url: data.url || '/home' },
        })
    );
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const url = (event.notification.data && event.notification.data.url) || '/home';
    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then((clients) => {
                for (const client of clients) {
                    if ('focus' in client) {
                        client.navigate(url);
                        return client.focus();
                    }
                }
                return self.clients.openWindow ? self.clients.openWindow(url) : null;
            })
    );
});

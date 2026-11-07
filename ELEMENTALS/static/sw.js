/* ELEMENTALS offline shell: pages and files needed to play without internet.
   Every path is resolved against this file, so the same worker covers the game
   on its own (scope "/") and the copy mounted at /game/ in the Review Center. */
var ROOT = new URL("./", self.location).pathname;
var CACHE = "elementals-v3";
var SHELL = [ROOT, ROOT + "table", ROOT + "install", ROOT + "static/style.css",
             ROOT + "static/app.js", ROOT + "static/game.js",
             ROOT + "manifest.webmanifest", ROOT + "icon/192"];

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) {
    return Promise.all(SHELL.map(function (u) { return c.add(u).catch(function () {}); }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    // Mounted inside the Review Center, this origin also holds the quiz app's
    // cache and the other games' caches. Only elementals-* is ours to clear.
    return Promise.all(keys.filter(function (k) {
      return k !== CACHE && k.indexOf("elementals-") === 0;
    }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (e) {
  var url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) { return; }

  // The game itself must talk to the database, so it is never served from cache.
  if (url.pathname.indexOf("/api/") > -1) { return; }

  if (e.request.mode === "navigate") {
    e.respondWith(fetch(e.request).then(function (r) {
      var copy = r.clone();
      caches.open(CACHE).then(function (c) { c.put(url.pathname, copy); });
      return r;
    }).catch(function () {
      return caches.match(e.request).then(function (m) { return m || caches.match(ROOT); });
    }));
    return;
  }

  // Icons and fonts rarely change, so they come from cache first.
  if (/(^|\/)(icon|assets)\//.test(url.pathname)) {
    e.respondWith(caches.match(e.request).then(function (hit) {
      if (hit) { return hit; }
      return fetch(e.request).then(function (r) {
        if (r.ok) { var copy = r.clone(); caches.open(CACHE).then(function (c) { c.put(e.request, copy); }); }
        return r;
      });
    }));
    return;
  }

  // Pages, styles and scripts are taken from the app when it is reachable, and
  // from the cache when the computer is offline.
  e.respondWith(fetch(e.request).then(function (r) {
    if (r.ok) { var copy = r.clone(); caches.open(CACHE).then(function (c) { c.put(e.request, copy); }); }
    return r;
  }).catch(function () {
    return caches.match(e.request).then(function (m) { return m || caches.match(ROOT); });
  }));
});

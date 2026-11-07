/* Crosswords offline shell. Paths resolve against this file, so the same
   worker covers the game on its own and the copy mounted at /games/crossword/. */
var ROOT = new URL("./", self.location).pathname;
var CACHE = "crossword-v2";
var SHELL = [ROOT, ROOT + "static/crossword.css", ROOT + "static/crossword.js",
             ROOT + "static/cw_export.js", ROOT + "manifest.webmanifest",
             ROOT + "icon/192"];

// A play board, a result sheet and every API answer belong to one student, and
// the PDFs carry their name - none of that may sit on a shared review tablet.
function isPrivate(pathname) {
  return /\/play\//.test(pathname) || /\/result\//.test(pathname) ||
         /\/pdf\//.test(pathname);
}

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) {
    return Promise.all(SHELL.map(function (u) { return c.add(u).catch(function () {}); }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    // Mounted inside the Review Center, this origin also holds the quiz app's
    // cache and the other games' caches. Only crossword-* is ours to clear.
    return Promise.all(keys.filter(function (k) {
      return k !== CACHE && k.indexOf("crossword-") === 0;
    }).map(function (k) { return caches.delete(k); })).then(function () {
      return caches.open(CACHE).then(function (c) {
        return Promise.all(c.keys().then(function (requests) {
          return Promise.all(requests.filter(function (req) {
            return isPrivate(new URL(req.url).pathname);
          }).map(function (req) { return c.delete(req); }));
        }));
      });
    });
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (e) {
  var url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) { return; }

  var private = isPrivate(url.pathname);

  // A live attempt: the clock, the board and the scores always come from the server.
  if (url.pathname.indexOf("/api/") > -1 || private) { return; }

  if (/(^|\/)icon\//.test(url.pathname)) {
    e.respondWith(caches.match(e.request).then(function (hit) {
      return hit || fetch(e.request);
    }));
    return;
  }

  // Network first, cache only for a device that is offline between lessons.
  e.respondWith(fetch(e.request).then(function (r) {
    if (r.ok) {
      var copy = r.clone();
      caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
    }
    return r;
  }).catch(function () {
    return caches.match(e.request).then(function (m) { return m || caches.match(ROOT); });
  }));
});

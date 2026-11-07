/* Jumbled Letters offline shell. Paths resolve against this file, so the same
   worker covers the game on its own and the copy mounted at /games/jumbled/. */
var ROOT = new URL("./", self.location).pathname;
var CACHE = "jumbled-v4";
var SHELL = [ROOT, ROOT + "scores", ROOT + "static/jumbled.css", ROOT + "static/jumbled.js",
             ROOT + "static/jl_setup.js", ROOT + "static/jl_export.js",
             ROOT + "manifest.webmanifest", ROOT + "icon/192"];

// A player's own name is printed on their result sheet, so that page and its
// picture must never be kept on a shared tablet for the next student to open.
function isPrivate(pathname) {
  return /\/result\//.test(pathname);
}

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) {
    return Promise.all(SHELL.map(function (u) { return c.add(u).catch(function () {}); }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    // Mounted inside the Review Center, this origin also holds the quiz app's
    // cache and the other games' caches. Only jumbled-* is ours to clear.
    return Promise.all(keys.filter(function (k) {
      return k !== CACHE && k.indexOf("jumbled-") === 0;
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

  // A round is live: the board, the clock and the answers always come from the server.
  if (url.pathname.indexOf("/api/") > -1 || private) { return; }

  if (/(^|\/)icon\//.test(url.pathname)) {
    e.respondWith(caches.match(e.request).then(function (hit) {
      return hit || fetch(e.request);
    }));
    return;
  }

  // Network first, cache only for a device that is offline mid-lesson.
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

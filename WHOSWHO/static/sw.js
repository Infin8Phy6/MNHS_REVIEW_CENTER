/* Who's Who offline shell. The activity JSON and the pictures are cached, so a
   round already opened keeps working when the classroom internet drops.
   A live room is different: its clock always comes from the server. */
var ROOT = new URL("./", self.location).pathname;
var CACHE = "whoswho-v3";
var SHELL = [ROOT, ROOT + "scores", ROOT + "static/whoswho.css", ROOT + "static/whoswho.js",
             ROOT + "static/ww_write.js", ROOT + "manifest.webmanifest", ROOT + "icon/192"];

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) {
    return Promise.all(SHELL.map(function (u) { return c.add(u).catch(function () {}); }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    // Mounted inside the Review Center, this origin also holds the quiz app's
    // cache and the other games' caches. Only whoswho-* is ours to clear.
    return Promise.all(keys.filter(function (k) {
      return k !== CACHE && k.indexOf("whoswho-") === 0;
    }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (e) {
  var url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) { return; }

  // The board, the clock and the answers are the round: never from a cache.
  if (url.pathname.indexOf("/api/") > -1) { return; }

  // Pictures and icons: cache first, they never change once written.
  if (/(^|\/)(photo|icon)\//.test(url.pathname)) {
    e.respondWith(caches.match(e.request).then(function (hit) {
      return hit || fetch(e.request).then(function (r) {
        if (r.ok) { var copy = r.clone(); caches.open(CACHE).then(function (c) { c.put(e.request, copy); }); }
        return r;
      });
    }));
    return;
  }

  // Everything else: network first, so an edited activity shows straight away.
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

// Linux Continuity Service Worker
const CACHE_NAME = "continuity-v1";
const ASSETS = [
  "/",
  "/static/css/style.css",
  "/static/css/xterm.css",
  "/static/js/app.js",
  "/static/js/xterm.js",
  "/static/js/xterm-addon-fit.js",
  "/static/icons/icon.png"
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((k) => {
          if (k !== CACHE_NAME) return caches.delete(k);
        })
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  // Only cache GET requests for static files, bypass API and websocket
  const url = new URL(e.request.url);
  if (e.request.method === "GET" && (url.pathname.startsWith("/static/") || url.pathname === "/")) {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(e.request))
    );
  }
});

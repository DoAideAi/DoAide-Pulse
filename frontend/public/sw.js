// v3: v2 kept /analytics-redact.js, /theme-init.js and /embed.js cache-first
// under a name no deploy changed, so returning visitors ran their first copy
// of each for good. Bumping the name drops those on activate.
const CACHE_NAME = "doaide-pulse-v3";
const STATIC_ASSETS = ["/", "/favicon.svg", "/icon-192.png", "/icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_NAME)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const { request } = e;
  const url = new URL(request.url);

  if (request.method !== "GET") return;

  // The API is never cached: its responses are per-account, and a cached copy
  // would outlive a sign-out on a shared machine.
  if (url.pathname.startsWith("/api")) return;

  // Cache-first only where a new file always has a new name: Vite's hashed
  // /assets/ and the font CDN. Everything else — the unhashed scripts in
  // public/ above all — changes in place, and goes to the network first below.
  if (
    (url.origin === self.location.origin && url.pathname.startsWith("/assets/")) ||
    url.hostname === "fonts.googleapis.com" ||
    url.hostname === "fonts.gstatic.com"
  ) {
    e.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((res) => {
            const clone = res.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
            return res;
          })
      )
    );
    return;
  }

  e.respondWith(
    fetch(request)
      .then((res) => {
        const clone = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        return res;
      })
      .catch(() =>
        caches.match(request).then((cached) => cached || caches.match("/"))
      )
  );
});

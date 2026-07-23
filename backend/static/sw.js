const CACHE = "stock-analyzer-static-v2";
const STATIC_PATHS = new Set([
  "/manifest.json",
  "/icon-192.png",
  "/icon-512.png",
  "/apple-touch-icon.png",
]);

self.addEventListener("install", (e) => {
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(names.filter((name) => name !== CACHE).map((name) => caches.delete(name)));
      await clients.claim();
    })()
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== self.location.origin || !STATIC_PATHS.has(url.pathname)) {
    return;
  }
  e.respondWith(
    (async () => {
      const cache = await caches.open(CACHE);
      try {
        const response = await fetch(e.request);
        cache.put(e.request, response.clone());
        return response;
      } catch {
        const cached = await cache.match(e.request);
        return cached || new Response("Offline", { status: 503 });
      }
    })()
  );
});

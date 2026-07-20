const CACHE = "stock-analyzer-v1";

self.addEventListener("install", (e) => {
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(clients.claim());
});

self.addEventListener("fetch", (e) => {
  e.respondWith(
    (async () => {
      const cache = await caches.open(CACHE);
      try {
        const response = await fetch(e.request);
        if (e.request.method === "GET") {
          cache.put(e.request, response.clone());
        }
        return response;
      } catch {
        const cached = await cache.match(e.request);
        return cached || new Response("Offline", { status: 503 });
      }
    })()
  );
});

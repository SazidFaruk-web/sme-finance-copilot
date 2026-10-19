// Cache the public application shell only. Business API requests always go to the server.
const CACHE = "sme-shell-36";
const FILES = ["/", "/static/app.js?v=34", "/static/settings.js?v=1", "/static/settings.css?v=1", "/static/pilot.js?v=23", "/static/pilot-store.js?v=14", "/static/voice.js?v=1",
  "/static/pilot.css?v=15", "/static/styles.css?v=19", "/static/guided.css?v=17", "/static/auth.css?v=15",
  "/static/auth.js?v=21", "/static/auth-copy.js?v=18", "/static/icons.js?v=13", "/static/charts.js?v=9", "/static/guided-pages.js?v=20",
  "/static/guidance.js?v=19", "/static/i18n-zh.js?v=6", "/static/market.js?v=5", "/static/market.css?v=4", "/static/tour.js?v=2", "/static/tour.css?v=2", "/static/home-note.js?v=2", "/static/manifest.webmanifest", "/static/app-icon.svg?v=2", "/static/app-icon-192.png?v=2", "/static/apple-touch-icon.png?v=2"];
self.addEventListener("install", event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(FILES))));
self.addEventListener("activate", event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith("sme-shell-") && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request).catch(() => caches.match("/"))); return;
  }
  if (!url.pathname.startsWith("/static/")) return;
  // Module requests may add an Origin header that install-time requests lack.
  // These allowlisted public files have identical content for every origin/user.
  if (!FILES.includes(url.pathname + url.search)) return;
  event.respondWith(caches.match(event.request, { ignoreVary: true }).then(hit => hit || fetch(event.request)));
});

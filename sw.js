// 圖片本機快取:samples/ 與 cards/ 載過一次就存 CacheStorage,回訪不再重載。
// 注意:若「原地覆蓋」既有圖片(同檔名換內容),必須 bump 下面的 CACHE 版本,
// 否則舊訪客永遠看快取。每日新增字體是新檔名,不用動版本。
const CACHE = "afs-v3";
const IMMUTABLE = /\/(samples|cards)\//;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(
  caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim())
));

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;

  if (IMMUTABLE.test(url.pathname)) {
    // 圖片:cache-first,命中即回、不打網路
    e.respondWith(caches.open(CACHE).then(c =>
      c.match(e.request).then(hit => hit || fetch(e.request).then(res => {
        if (res.ok) c.put(e.request, res.clone());
        return res;
      }))
    ));
  } else {
    // index.html / fonts.json:network-first(每日更新要進得來),離線退快取
    e.respondWith(
      fetch(e.request).then(res => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, copy));
        }
        return res;
      }).catch(() => caches.match(e.request, { ignoreSearch: true }))
    );
  }
});

// 圖片本機快取:samples/ 與 cards/ 走 stale-while-revalidate——先回快取(快),
// 同時背景打一次網路確認 repo 上的檔案有沒有更新,有更新就存回快取,下次造訪
// 自動拿到新的。原地覆蓋既有圖片(同檔名換內容)不用再手動 bump 版本。
const CACHE = "afs-v9";
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
    // 圖片:stale-while-revalidate——命中先回快取,背景照樣打網路更新快取
    e.respondWith(caches.open(CACHE).then(async c => {
      const hit = await c.match(e.request);
      const network = fetch(e.request).then(res => {
        if (res.ok) c.put(e.request, res.clone());
        return res;
      }).catch(() => hit);
      return hit || network;
    }));
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

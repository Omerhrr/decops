/* DecOps service worker. Deliberately minimal and safe for a private app:
   - NEVER caches /api/ or any authenticated page (no data at rest in the cache).
   - Caches only static build assets, and shows a small offline page when a
     navigation fails because the device is offline. */
const CACHE = 'decops-static-v1'
const OFFLINE = '/offline.html'

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then(c => c.addAll([OFFLINE, '/icon-192.png'])).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return

  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).catch(() => caches.match(OFFLINE)))
    return
  }
  if (url.pathname.startsWith('/_nuxt/')) { // content-hashed, safe to cache
    event.respondWith(
      caches.match(req).then(hit => hit || fetch(req).then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)) }
        return res
      })),
    )
  }
})

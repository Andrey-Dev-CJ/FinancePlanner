const CACHE = 'finplan-v4';

// Новый worker вступает в силу СРАЗУ, вытесняя старый
self.addEventListener('install', () => {
    self.skipWaiting();
});

// При активации — чистим старые кэши и забираем управление
self.addEventListener('activate', (e) => {
    e.waitUntil(
        caches.keys()
            .then(keys => Promise.all(
                keys.filter(k => k !== CACHE).map(k => caches.delete(k))
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (e) => {
    if (e.request.method !== 'GET') return;

    const url = new URL(e.request.url);

    // Кэшируем ТОЛЬКО http/https — пропускаем chrome-extension://, devtools:// и т.п.
    if (!url.protocol.startsWith('http')) return;

    // API и auth — всегда из сети
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/auth/')) return;

    // Остальное — network-first с фолбэком на кэш
    e.respondWith(
        fetch(e.request)
            .then(res => {
                const copy = res.clone();
                caches.open(CACHE).then(c => c.put(e.request, copy));
                return res;
            })
            .catch(() => caches.match(e.request))
    );
});
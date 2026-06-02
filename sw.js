// PhoneLink Service Worker — enables offline PWA + Add to Home Screen
const CACHE_NAME = 'phonelink-v1';
const ASSETS = [
    './',
    './phone_ui.html',
    './icon-512.png',
    './manifest.json'
];

self.addEventListener('install', e => {
    e.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS))
    );
    self.skipWaiting();
});

self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', e => {
    const url = new URL(e.request.url);
    // Only cache static assets, never API calls
    if (url.pathname.startsWith('/ping') || url.pathname.startsWith('/apps') ||
        url.pathname.startsWith('/gallery') || url.pathname.startsWith('/shell') ||
        url.pathname.startsWith('/metrics') || url.pathname.startsWith('/status') ||
        url.pathname.startsWith('/call') || url.pathname.startsWith('/sms') ||
        url.pathname.startsWith('/inbox') || url.pathname.startsWith('/url') ||
        url.pathname.startsWith('/flash') || url.pathname.startsWith('/volume') ||
        url.pathname.startsWith('/wake') || url.pathname.startsWith('/screenshot') ||
        url.pathname.startsWith('/fix') || url.pathname.startsWith('/wifi') ||
        url.pathname.startsWith('/forward') || url.pathname.startsWith('/type') ||
        url.pathname.startsWith('/app') || url.pathname.startsWith('/disconnect') ||
        url.pathname.startsWith('/power') || url.pathname.startsWith('/clip') ||
        url.pathname.startsWith('/cam') || url.pathname.startsWith('/macro') ||
        url.pathname.startsWith('/stealth') || url.pathname.startsWith('/bug') ||
        url.pathname.startsWith('/2fa') || url.pathname.startsWith('/gps') ||
        url.pathname.startsWith('/notifs') || url.pathname.startsWith('/ui-dump')
    ) {
        return; // Let API requests pass through to the network
    }
    e.respondWith(
        caches.match(e.request).then(cached => cached || fetch(e.request))
    );
});

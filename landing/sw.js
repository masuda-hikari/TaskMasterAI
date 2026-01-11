// TaskMasterAI Service Worker
// キャッシュ戦略: Stale-While-Revalidate + Network First for API

const CACHE_NAME = 'taskmaster-v1';
const STATIC_CACHE = 'taskmaster-static-v1';
const API_CACHE = 'taskmaster-api-v1';

// 静的リソース（プリキャッシュ対象）
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/privacy.html',
  '/terms.html',
  '/contact.html',
  '/manifest.json',
  '/offline.html'
];

// インストール時にプリキャッシュ
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => {
        console.log('[SW] Caching static assets');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => self.skipWaiting())
  );
});

// アクティベート時に古いキャッシュを削除
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(cacheNames => {
        return Promise.all(
          cacheNames
            .filter(name => name !== STATIC_CACHE && name !== API_CACHE)
            .map(name => caches.delete(name))
        );
      })
      .then(() => self.clients.claim())
  );
});

// フェッチ時のキャッシュ戦略
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // APIリクエスト: Network First
  if (url.pathname.startsWith('/api/') ||
      url.pathname.startsWith('/beta/') ||
      url.pathname.startsWith('/demo/') ||
      url.pathname.startsWith('/admin/')) {
    event.respondWith(networkFirst(request));
    return;
  }

  // 静的リソース: Stale While Revalidate
  if (request.destination === 'document' ||
      request.destination === 'script' ||
      request.destination === 'style' ||
      request.destination === 'image' ||
      request.destination === 'font') {
    event.respondWith(staleWhileRevalidate(request));
    return;
  }

  // その他: Network First with Fallback
  event.respondWith(networkFirstWithFallback(request));
});

// Network First 戦略
async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(API_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) return cached;
    throw error;
  }
}

// Stale While Revalidate 戦略
async function staleWhileRevalidate(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);

  // バックグラウンドで更新
  const fetchPromise = fetch(request).then(response => {
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  }).catch(() => null);

  // キャッシュがあればすぐに返す
  if (cached) {
    return cached;
  }

  // キャッシュがなければネットワークから取得
  const response = await fetchPromise;
  if (response) return response;

  // オフラインページにフォールバック
  return caches.match('/offline.html');
}

// Network First with Fallback
async function networkFirstWithFallback(request) {
  try {
    const response = await fetch(request);
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) return cached;

    // HTMLリクエストならオフラインページ
    if (request.destination === 'document') {
      return caches.match('/offline.html');
    }

    throw error;
  }
}

// プッシュ通知（将来拡張用）
self.addEventListener('push', event => {
  if (!event.data) return;

  const data = event.data.json();
  const options = {
    body: data.body || 'TaskMasterAIからの通知です',
    icon: '/icons/icon-192x192.png',
    badge: '/icons/badge-72x72.png',
    vibrate: [100, 50, 100],
    data: {
      dateOfArrival: Date.now(),
      url: data.url || '/'
    },
    actions: data.actions || []
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'TaskMasterAI', options)
  );
});

// 通知クリック時の処理
self.addEventListener('notificationclick', event => {
  event.notification.close();

  const url = event.notification.data?.url || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then(windowClients => {
      // 既存のウィンドウがあればフォーカス
      for (const client of windowClients) {
        if (client.url === url && 'focus' in client) {
          return client.focus();
        }
      }
      // なければ新規ウィンドウを開く
      if (clients.openWindow) {
        return clients.openWindow(url);
      }
    })
  );
});

// バックグラウンド同期（将来拡張用）
self.addEventListener('sync', event => {
  if (event.tag === 'sync-beta-signup') {
    event.waitUntil(syncBetaSignup());
  }
});

async function syncBetaSignup() {
  // IndexedDBからペンディング登録を取得して送信
  // 実装は将来の拡張で追加
  console.log('[SW] Background sync: beta signup');
}

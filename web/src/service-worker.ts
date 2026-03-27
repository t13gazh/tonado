/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />

import { build, files, version } from '$service-worker';

const sw = self as unknown as ServiceWorkerGlobalScope;

const CACHE_NAME = `tonado-${version}`;

// Assets to pre-cache: built JS/CSS + static files
const PRECACHE = [...build, ...files];

sw.addEventListener('install', (event) => {
	event.waitUntil(
		caches
			.open(CACHE_NAME)
			.then((cache) => cache.addAll(PRECACHE))
			.then(() => sw.skipWaiting()),
	);
});

sw.addEventListener('activate', (event) => {
	event.waitUntil(
		caches.keys().then((keys) =>
			Promise.all(
				keys
					.filter((key) => key !== CACHE_NAME)
					.map((key) => caches.delete(key)),
			),
		).then(() => sw.clients.claim()),
	);
});

sw.addEventListener('fetch', (event) => {
	const url = new URL(event.request.url);

	// Skip API requests and WebSocket — always go to network
	if (url.pathname.startsWith('/api') || url.pathname === '/ws') {
		return;
	}

	// For app shell and assets: cache-first, fallback to network
	if (event.request.method === 'GET') {
		event.respondWith(
			caches.match(event.request).then((cached) => {
				if (cached) return cached;

				return fetch(event.request).then((response) => {
					// Cache successful responses
					if (response.ok) {
						const clone = response.clone();
						caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
					}
					return response;
				});
			}).catch(() => {
				// Offline fallback: return the app shell
				if (event.request.mode === 'navigate') {
					return caches.match('/index.html') as Promise<Response>;
				}
				return new Response('Offline', { status: 503 });
			}),
		);
	}
});

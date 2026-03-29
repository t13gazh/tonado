/**
 * Global browser audio state for MPD HTTP stream playback.
 * Lives in a store so it persists across page navigation.
 *
 * IMPORTANT: This module ONLY controls the HTML Audio element.
 * It does NOT toggle MPD outputs — the httpd output must stay enabled
 * independently, otherwise MPD stops playback when its last output is disabled.
 */

let audioElement: HTMLAudioElement | null = null;
let _active = $state(false);
let _loading = $state(false);
let _retryTimer: ReturnType<typeof setTimeout> | null = null;
let _retryCount = 0;
const MAX_RETRIES = 5;
const RETRY_DELAY_MS = 2000;

export function getBrowserAudioActive(): boolean {
	return _active;
}

export function getBrowserAudioLoading(): boolean {
	return _loading;
}

function streamUrl(): string {
	return `/api/player/stream?t=${Date.now()}`;
}

function clearRetry(): void {
	if (_retryTimer) {
		clearTimeout(_retryTimer);
		_retryTimer = null;
	}
	_retryCount = 0;
}

function retryStream(): void {
	if (!_active || !audioElement || _retryCount >= MAX_RETRIES) {
		_loading = false;
		_active = false;
		clearRetry();
		return;
	}
	_retryCount++;
	_loading = true;
	_retryTimer = setTimeout(() => {
		if (!_active || !audioElement) return;
		audioElement.src = streamUrl();
		audioElement.load();
		audioElement.play().catch(() => { retryStream(); });
	}, RETRY_DELAY_MS);
}

export function setBrowserAudioElement(el: HTMLAudioElement): void {
	audioElement = el;
	el.addEventListener('playing', () => {
		_loading = false;
		clearRetry();
	});
	el.addEventListener('waiting', () => {
		if (_active) _loading = true;
	});
	el.addEventListener('error', () => {
		if (_active && !_reloadTimer) {
			// Only retry if no reload is already scheduled (track change)
			retryStream();
		} else if (!_active) {
			_loading = false;
		}
	});
}

export function startBrowserAudio(): void {
	if (!audioElement) return;
	clearRetry();
	_loading = true;
	_active = true;
	audioElement.src = streamUrl();
	audioElement.load();
	audioElement.play().catch(() => { retryStream(); });
}

export function stopBrowserAudio(): void {
	clearRetry();
	if (_reloadTimer) {
		clearTimeout(_reloadTimer);
		_reloadTimer = null;
	}
	if (audioElement) {
		audioElement.pause();
		audioElement.src = '';
	}
	_active = false;
	_loading = false;
}

/**
 * Reload the stream (e.g. after track change).
 * Only acts if browser audio is currently active.
 * Waits briefly so MPD has time to buffer the new track
 * on its httpd output before the browser requests the proxy.
 */
let _reloadTimer: ReturnType<typeof setTimeout> | null = null;
const RELOAD_DELAY_MS = 2500;

export function reloadBrowserAudio(): void {
	if (!_active || !audioElement) return;
	clearRetry();
	// Cancel any pending reload (rapid track changes)
	if (_reloadTimer) {
		clearTimeout(_reloadTimer);
	}
	// Immediately stop old stream to prevent error events from stale connection
	audioElement.pause();
	audioElement.removeAttribute('src');
	audioElement.load();
	_loading = true;
	_reloadTimer = setTimeout(() => {
		_reloadTimer = null;
		if (!_active || !audioElement) return;
		audioElement.src = streamUrl();
		audioElement.load();
		audioElement.play().catch(() => {
			retryStream();
		});
	}, RELOAD_DELAY_MS);
}

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
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1500;

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
		audioElement.play().catch(() => { _loading = false; });
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
		if (_active) {
			retryStream();
		} else {
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
	audioElement.play().catch(() => { _loading = false; });
}

export function stopBrowserAudio(): void {
	clearRetry();
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
 */
export function reloadBrowserAudio(): void {
	if (!_active || !audioElement) return;
	clearRetry();
	audioElement.src = streamUrl();
	audioElement.load();
	audioElement.play().catch(() => { _loading = false; });
}

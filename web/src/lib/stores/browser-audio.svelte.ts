/**
 * Global browser audio state for MPD HTTP stream playback.
 * Lives in a store so it persists across page navigation.
 *
 * IMPORTANT: This module ONLY controls the HTML Audio element.
 * It does NOT toggle MPD outputs — the httpd output must stay enabled
 * independently, otherwise MPD stops playback when its last output is disabled.
 *
 * Reload-on-track-change is driven by the backend's ``player_stream_ready``
 * WebSocket event (see player.svelte.ts), NOT a client-side timeout.  The
 * backend knows when MPD's httpd encoder is actually ready; the old 2.5 s
 * guess-and-retry dance raced the encoder and frequently cut the audio.
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
		if (_active) {
			// Backend-driven reloads are deterministic — any error that
			// reaches us here is a genuine proxy/MPD problem, so retry.
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
	audioElement.play().catch(() => { retryStream(); });
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
 * Reload the stream.  Called by the WebSocket subscriber on
 * ``player_stream_ready`` — at that point the backend has verified that
 * MPD's httpd encoder is actually producing bytes for the new track, so
 * we can reconnect immediately without a client-side delay.
 *
 * Only acts if browser audio is currently active.
 */
export function reloadBrowserAudio(): void {
	if (!_active || !audioElement) return;
	clearRetry();
	_loading = true;
	// Swap src directly — the browser closes the stale connection when
	// the new one starts loading.  No pause/removeAttribute dance needed
	// now that the backend guarantees the new stream is live.
	audioElement.src = streamUrl();
	audioElement.load();
	audioElement.play().catch(() => { retryStream(); });
}

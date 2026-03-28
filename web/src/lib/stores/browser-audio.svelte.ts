/**
 * Global browser audio state for MPD HTTP stream playback.
 * Lives in a store so it persists across page navigation.
 */

let audioElement: HTMLAudioElement | null = null;
let _active = $state(false);
let _loading = $state(false);

export function getBrowserAudioActive(): boolean {
	return _active;
}

export function getBrowserAudioLoading(): boolean {
	return _loading;
}

export function setBrowserAudioElement(el: HTMLAudioElement): void {
	audioElement = el;
	el.addEventListener('playing', () => { _loading = false; });
	el.addEventListener('waiting', () => { if (_active) _loading = true; });
	el.addEventListener('error', () => { _loading = false; _active = false; });
}

export function startBrowserAudio(): void {
	if (!audioElement) return;
	_loading = true;
	_active = true;
	audioElement.src = `/api/player/stream`;
	audioElement.load();
	audioElement.play().catch(() => { _loading = false; });
}

export function stopBrowserAudio(): void {
	if (audioElement) {
		audioElement.pause();
		audioElement.src = '';
	}
	_active = false;
	_loading = false;
}

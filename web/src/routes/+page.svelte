<script lang="ts">
	import { t } from '$lib/i18n';
	import { player, authApi, library } from '$lib/api';
	import { getPlayerState, getSleepTimer, setSleepTimer } from '$lib/stores/player.svelte';
	import HealthBanner from '$lib/components/HealthBanner.svelte';
	import CoverArt from '$lib/components/CoverArt.svelte';
	import { formatTime, parseTrackName } from '$lib/utils';
	import { getBrowserAudioActive, getBrowserAudioLoading, startBrowserAudio, stopBrowserAudio, reloadBrowserAudio } from '$lib/stores/browser-audio.svelte';
	import { isMpdConnected } from '$lib/stores/health.svelte';
	import { addToast } from '$lib/stores/toast.svelte';
	import { tick, onMount } from 'svelte';

	const mpdOk = $derived(isMpdConnected());
	const state = $derived(getPlayerState());
	const isPlaying = $derived(state.state === 'playing');
	const isStopped = $derived(state.state === 'stopped');
	const hasTrack = $derived(state.current_track !== '');
	const isLastTrack = $derived(state.playlist_position >= state.playlist_length - 1);
	const canPlay = $derived(hasTrack || state.playlist_length > 0);
	const canSeek = $derived(!state.is_stream && state.duration > 0);
	const hasQueue = $derived(state.playlist_length > 1);
	const isLiveStream = $derived(state.is_stream && state.playlist_length <= 1);
	const trackInfo = $derived(parseTrackName(state.current_track));

	// Cover source: only for local tracks (not streams/podcasts with absolute URLs).
	// current_uri is the MPD URI — a relative path for local files, an http(s) URL otherwise.
	const coverSrc = $derived.by(() => {
		if (!hasTrack) return undefined;
		const uri = state.current_uri;
		if (!uri || state.is_stream) return undefined;
		if (uri.startsWith('http://') || uri.startsWith('https://')) return undefined;
		return library.coverUrl(uri, 'track');
	});
	const coverTitle = $derived(trackInfo.title || state.current_album || 'Tonado');

	let volumeChanging = $state(false);
	let localVolume = $state(50);
	let muted = $state(false);
	let outputs = $state<{ id: number; name: string; enabled: boolean }[]>([]);
	const browserPlaying = $derived(getBrowserAudioActive());
	const browserLoading = $derived(getBrowserAudioLoading());
	let premuteVolume = $state(50);
	const shuffleOn = $derived(state.shuffle);
	let seekDragging = $state(false);
	let seekOverride = $state(false);
	let seekThumbVisible = $state(false);
	let seekLocalProgress = $state(0);
	let seekHideTimer: ReturnType<typeof setTimeout> | null = null;

	const progress = $derived((seekDragging || seekOverride) ? seekLocalProgress : (state.duration > 0 ? (state.elapsed / state.duration) * 100 : 0));

	$effect(() => {
		if (!volumeChanging) {
			localVolume = state.volume;
		}
	});

	function handleVolumeStart() {
		volumeChanging = true;
	}

	function handleVolumeEnd() {
		const v = localVolume;
		player.volume(v).then(() => {
			localVolume = v;
			volumeChanging = false;
		}).catch(() => {
			volumeChanging = false;
		});
	}

	function toggleMute() {
		if (muted) {
			muted = false;
			localVolume = premuteVolume;
			player.volume(premuteVolume);
		} else {
			premuteVolume = localVolume;
			muted = true;
			localVolume = 0;
			player.volume(0);
		}
	}

	function toggleShuffle() {
		player.toggleRandom();
	}

	function getSeekRatio(e: PointerEvent | MouseEvent): number {
		const bar = e.currentTarget as HTMLElement;
		const rect = bar.getBoundingClientRect();
		return Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
	}

	function handleSeekDragStart(e: PointerEvent) {
		seekDragging = true;
		seekThumbVisible = true;
		seekLocalProgress = getSeekRatio(e) * 100;
		(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
	}

	function handleSeekDragMove(e: PointerEvent) {
		if (!seekDragging) return;
		seekLocalProgress = getSeekRatio(e) * 100;
	}

	function handleSeekDragEnd(e: PointerEvent) {
		if (seekDragging) {
			const ratio = seekLocalProgress / 100;
			seekDragging = false;
			seekOverride = true;
			player.seek(ratio * state.duration).then(() => { seekOverride = false; }).catch(() => { seekOverride = false; });
		}
		showSeekThumb();
	}

	function handleSeekClick(e: MouseEvent) {
		if (seekDragging) return;
		const bar = e.currentTarget as HTMLElement;
		const rect = bar.getBoundingClientRect();
		const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
		seekLocalProgress = ratio * 100;
		seekOverride = true;
		player.seek(ratio * state.duration).then(() => { seekOverride = false; }).catch(() => { seekOverride = false; });
		showSeekThumb();
	}

	function showSeekThumb() {
		seekThumbVisible = true;
		if (seekHideTimer) clearTimeout(seekHideTimer);
		seekHideTimer = setTimeout(() => { seekThumbVisible = false; }, 2000);
	}

	function marquee(node: HTMLElement) {
		function setup() {
			const span = node.querySelector('.marquee-text') as HTMLElement;
			if (!span) return;
			span.style.animation = 'none';
			span.style.transform = '';
			node.classList.remove('marquee-active');
			requestAnimationFrame(() => {
				const overflow = span.scrollWidth - node.clientWidth;
				if (overflow > 5) {
					node.classList.add('marquee-active');
					// Recalculate with padding applied
					requestAnimationFrame(() => {
						const newOverflow = span.scrollWidth - node.clientWidth;
						const scrollDuration = Math.max(4, newOverflow / 25);
						const totalDuration = scrollDuration + 3;
						span.style.setProperty('--marquee-distance', `-${newOverflow + 16}px`);
						span.style.animation = `marquee-scroll ${totalDuration}s ease-in-out infinite`;
					});
				}
			});
		}
		setup();
		return { update: () => { tick().then(setup); } };
	}

	let lastTrackUri = $state('');
	let lastPlayState = $state('');

	// Sleep timer state — authoritative snapshot lives in the player store
	// (fed by WebSocket `sleep_timer` events + REST poll fallback); the
	// local `sleepTick` drives the countdown display between updates.
	const sleepSnapshot = $derived(getSleepTimer());
	let sleepTick = $state(0); // monotonic ms, bumped once per second while active
	let sleepCancelling = $state(false);
	let sleepMenuOpen = $state(false);
	let sleepExtending = $state(false);
	let sleepPillRef: HTMLDivElement | null = $state(null);
	let sleepMenuRef: HTMLDivElement | null = $state(null);
	let sleepTriggerRef: HTMLButtonElement | null = $state(null);
	let sleepExtend5Ref: HTMLButtonElement | null = $state(null);
	let sleepExtend10Ref: HTMLButtonElement | null = $state(null);
	let sleepCancelRef: HTMLButtonElement | null = $state(null);

	// Compute remaining seconds from the last authoritative snapshot plus
	// wall-clock drift since it arrived. `sleepTick` forces a recompute.
	const sleepRemaining = $derived.by(() => {
		sleepTick; // subscribe to tick
		if (!sleepSnapshot.active || sleepSnapshot.fading) return sleepSnapshot.remaining_seconds;
		const driftSec = sleepSnapshot.received_at
			? Math.max(0, (performance.now() - sleepSnapshot.received_at) / 1000)
			: 0;
		return Math.max(0, Math.floor(sleepSnapshot.remaining_seconds - driftSec));
	});
	const sleepFading = $derived(sleepSnapshot.active && sleepSnapshot.fading);
	const sleepVisible = $derived(sleepSnapshot.active && (sleepFading || sleepRemaining > 0));
	const sleepFinalMinute = $derived(sleepVisible && !sleepFading && sleepRemaining < 60);
	// Display label:
	// - fading → dedicated text, no countdown
	// - < 60s → per-second "Noch X Sek."
	// - >= 60s → per-minute "X Min." (quantized so the label only flips on minute boundaries)
	const sleepLabel = $derived.by(() => {
		if (sleepFading) return t('player.sleep_fading');
		if (sleepRemaining < 60) {
			return t('player.sleep_seconds', { seconds: Math.max(0, sleepRemaining) });
		}
		return t('player.sleep_minutes', { minutes: Math.floor(sleepRemaining / 60) });
	});
	// Stable text for screen readers: only changes on minute boundaries, fade entry, or final-minute entry
	const sleepAnnounce = $derived.by(() => {
		if (!sleepVisible) return '';
		if (sleepFading) return t('player.sleep_fading');
		if (sleepRemaining < 60) return t('player.sleep_announce_final');
		return t('player.sleep_announce_minutes', { minutes: Math.floor(sleepRemaining / 60) });
	});

	async function pollSleepTimer() {
		if (sleepCancelling) return; // avoid overwriting optimistic cancel state
		try {
			const res = await authApi.sleepTimer();
			setSleepTimer({
				active: res.active,
				remaining_seconds: Math.max(0, Math.floor(res.remaining_seconds)),
				fading: !!res.fading,
			});
		} catch {
			// On failure: keep last known state to avoid flicker
		}
	}

	async function cancelSleepTimer() {
		if (sleepCancelling) return;
		sleepCancelling = true;
		try {
			await authApi.cancelSleepTimer();
			setSleepTimer({ active: false, remaining_seconds: 0, fading: false });
			sleepMenuOpen = false;
		} catch {
			addToast(t('player.sleep_cancel_failed'), 'error');
		} finally {
			sleepCancelling = false;
		}
	}

	function toggleSleepMenu() {
		if (!sleepVisible) return;
		// During fade-out extend/cancel buttons make no functional sense:
		// the backend rejects /extend with 409 and cancel cannot un-stop
		// the imminent playback halt cleanly. Keep the menu closed.
		if (sleepFading) return;
		sleepMenuOpen = !sleepMenuOpen;
	}

	function closeSleepMenu(returnFocus: boolean = true) {
		if (!sleepMenuOpen) return;
		sleepMenuOpen = false;
		if (returnFocus) {
			// Return focus to the trigger pill (WAI-ARIA APG menu pattern)
			queueMicrotask(() => sleepTriggerRef?.focus());
		}
	}

	// Auto-focus first menu item when menu opens (WAI-ARIA APG menu pattern)
	$effect(() => {
		if (sleepMenuOpen) {
			queueMicrotask(() => sleepExtend5Ref?.focus());
		}
	});

	function sleepMenuItems(): HTMLButtonElement[] {
		return [sleepExtend5Ref, sleepExtend10Ref, sleepCancelRef].filter(
			(el): el is HTMLButtonElement => el !== null,
		);
	}

	function handleSleepMenuItemKeydown(e: KeyboardEvent) {
		const items = sleepMenuItems();
		if (items.length === 0) return;
		const currentIndex = items.indexOf(document.activeElement as HTMLButtonElement);
		if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
			e.preventDefault();
			const next = currentIndex < 0 ? 0 : (currentIndex + 1) % items.length;
			items[next]?.focus();
		} else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
			e.preventDefault();
			const prev = currentIndex <= 0 ? items.length - 1 : currentIndex - 1;
			items[prev]?.focus();
		} else if (e.key === 'Home') {
			e.preventDefault();
			items[0]?.focus();
		} else if (e.key === 'End') {
			e.preventDefault();
			items[items.length - 1]?.focus();
		}
		// Tab is NOT intercepted — lets focus leave the menu naturally.
	}

	async function extendSleepTimer(minutes: number) {
		if (sleepExtending) return;
		sleepExtending = true;
		try {
			const res = await authApi.extendSleepTimer(minutes);
			const remaining = Math.max(0, Math.floor(res.remaining_seconds));
			setSleepTimer({
				active: remaining > 0,
				remaining_seconds: remaining,
				fading: false,
			});
			closeSleepMenu(true);
			addToast(t('player.sleep_extended_toast', { minutes }), 'success');
		} catch {
			addToast(t('player.sleep_extend_failed'), 'error');
		} finally {
			sleepExtending = false;
		}
	}

	function handleSleepMenuKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && sleepMenuOpen) {
			closeSleepMenu(true);
		}
	}

	function handleSleepDocClick(e: MouseEvent) {
		if (!sleepMenuOpen) return;
		const target = e.target as Node;
		if (sleepMenuRef?.contains(target)) return;
		if (sleepPillRef?.contains(target)) return;
		// Outside click → close without stealing focus from the clicked element
		closeSleepMenu(false);
	}

	// Constant 1s tick — keeps the 60s boundary transition crisp (an adaptive
	// 30s/1s cadence could leave the pill stuck at "1 Min." for up to 29s past
	// the boundary before re-binding at 1s). The re-render cost is negligible:
	// `sleepLabel` only changes on minute boundaries (>60s) or per-second in
	// the final minute, and `sleepAnnounce` stays stable across whole minutes
	// so aria-live screen readers only speak on minute flips / final-minute
	// entry / fade entry. During fade-out no tick is needed.
	$effect(() => {
		if (!sleepSnapshot.active || sleepSnapshot.fading) return;
		// Re-enter on each snapshot change (start/extend/cancel/fade)
		void sleepSnapshot.received_at;
		const id = setInterval(() => { sleepTick = performance.now(); }, 1000);
		return () => clearInterval(id);
	});

	onMount(() => {
		player.outputs().then(o => { outputs = o; }).catch(() => {});

		pollSleepTimer();
		// WebSocket pushes authoritative updates; poll only as a fallback
		// in case the socket drops silently. 30s is fine for recovery.
		const pollId = setInterval(pollSleepTimer, 30_000);
		// Resync on tab focus: setInterval throttles to ~1/min in hidden tabs
		const onVisible = () => { if (!document.hidden) pollSleepTimer(); };
		document.addEventListener('visibilitychange', onVisible);

		// Sleep-menu: Escape + outside click
		document.addEventListener('keydown', handleSleepMenuKeydown);
		document.addEventListener('click', handleSleepDocClick);

		return () => {
			clearInterval(pollId);
			document.removeEventListener('visibilitychange', onVisible);
			document.removeEventListener('keydown', handleSleepMenuKeydown);
			document.removeEventListener('click', handleSleepDocClick);
		};
	});

	// Reload browser audio stream when the current track changes
	// or when playback restarts (same URI after stop→play cycle)
	$effect(() => {
		const uri = state.current_uri;
		const playState = state.state;
		const uriChanged = uri !== '' && uri !== lastTrackUri && lastTrackUri !== '';
		const restarted = uri !== '' && uri === lastTrackUri && lastPlayState === 'stopped' && playState === 'playing';
		if (uriChanged || restarted) {
			reloadBrowserAudio();
		}
		lastTrackUri = uri;
		lastPlayState = playState;
	});

	async function toggleBrowserAudio() {
		if (browserPlaying) {
			stopBrowserAudio();
		} else {
			// Ensure MPD httpd output is enabled before starting
			const browserOut = outputs.find(o => o.name === 'Browser');
			if (browserOut && !browserOut.enabled) {
				await player.toggleOutput(browserOut.id, true);
				outputs = await player.outputs();
			}
			startBrowserAudio();
		}
	}

	function handleToggle() {
		if (state.state === 'stopped' && state.playlist_length > 0) {
			player.play();
		} else {
			player.toggle();
		}
	}


</script>

<div class="relative flex flex-col items-center justify-center h-full px-6 py-8 gap-6">

	<!-- Sleep timer indicator: absolute so it does not push cover art down -->
	{#if sleepVisible}
		<div bind:this={sleepPillRef} class="absolute top-4 left-1/2 -translate-x-1/2 z-10">
			<button
				bind:this={sleepTriggerRef}
				type="button"
				onclick={toggleSleepMenu}
				aria-haspopup={sleepFading ? undefined : 'menu'}
				aria-expanded={sleepFading ? undefined : sleepMenuOpen}
				aria-disabled={sleepFading || undefined}
				aria-label={sleepFading ? t('player.sleep_fading') : t('player.sleep_menu_aria')}
				class="flex items-center gap-1 pl-3 pr-3 py-1.5 rounded-full text-xs shadow-sm transition-colors min-h-11 touch-manipulation hover:opacity-90 active:scale-95 {sleepFading ? 'bg-primary/20 text-primary cursor-default' : sleepFinalMinute ? 'bg-primary/15 text-primary' : 'bg-surface-light text-text-muted'}"
			>
				<svg class="w-4 h-4 {sleepFading ? 'animate-pulse' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
					<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
				</svg>
				<span class="font-medium" aria-hidden="true">
					{#if sleepFading}{t('player.sleep_fading')}{:else}{t('player.sleep_remaining', { time: sleepLabel })}{/if}
				</span>
				<span class="sr-only" aria-live="polite">{sleepAnnounce}</span>
			</button>

			{#if sleepMenuOpen && !sleepFading}
				<div
					bind:this={sleepMenuRef}
					role="menu"
					onkeydown={handleSleepMenuItemKeydown}
					class="absolute top-full left-1/2 -translate-x-1/2 mt-2 flex items-center gap-1 p-1 rounded-full bg-surface-light shadow-lg border border-surface-lighter animate-fade-up"
				>
					<button
						bind:this={sleepExtend5Ref}
						type="button"
						role="menuitem"
						onclick={() => extendSleepTimer(5)}
						disabled={sleepExtending}
						class="px-3 py-1.5 min-h-11 rounded-full text-xs font-medium text-text hover:bg-primary hover:text-white transition-colors disabled:opacity-40 touch-manipulation"
						aria-label={t('player.sleep_extend_5_aria')}
					>
						{t('player.sleep_extend_5')}
					</button>
					<button
						bind:this={sleepExtend10Ref}
						type="button"
						role="menuitem"
						onclick={() => extendSleepTimer(10)}
						disabled={sleepExtending}
						class="px-3 py-1.5 min-h-11 rounded-full text-xs font-medium text-text hover:bg-primary hover:text-white transition-colors disabled:opacity-40 touch-manipulation"
						aria-label={t('player.sleep_extend_10_aria')}
					>
						{t('player.sleep_extend_10')}
					</button>
					<button
						bind:this={sleepCancelRef}
						type="button"
						role="menuitem"
						onclick={cancelSleepTimer}
						disabled={sleepCancelling}
						class="p-2 min-h-11 min-w-11 flex items-center justify-center rounded-full text-text-muted hover:bg-surface-lighter hover:text-text transition-colors disabled:opacity-40 touch-manipulation"
						aria-label={t('player.sleep_cancel')}
					>
						<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
							<line x1="18" y1="6" x2="6" y2="18"/>
							<line x1="6" y1="6" x2="18" y2="18"/>
						</svg>
					</button>
				</div>
			{/if}
		</div>
	{/if}

	<!-- Cover Art -->
	<div class="w-64 h-64 sm:w-72 sm:h-72">
		{#if hasTrack}
			<!-- CoverArt reacts to `src`/`title` changes via $effect internally;
			     a {#key} wrapper would force a full remount and cause a flash. -->
			<CoverArt src={coverSrc} title={coverTitle} size="lg" eager />
		{:else}
			<div class="w-full h-full rounded-2xl bg-surface-light flex items-center justify-center shadow-xl">
				<svg class="w-20 h-20 text-text-muted opacity-30" viewBox="0 0 24 24" fill="currentColor">
					<path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55C7.79 13 6 14.79 6 17s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
				</svg>
			</div>
		{/if}
	</div>

	<!-- Track info below cover -->
	{#if hasTrack}
		<div class="text-center max-w-sm w-full overflow-hidden">
			{#if trackInfo.folder || state.current_album}
				<p class="text-xs text-text-muted truncate">{state.current_album || trackInfo.folder}</p>
			{/if}
			{#key trackInfo.title}
				<p class="text-lg font-semibold text-text mt-0.5 marquee-container animate-fade-up" use:marquee={trackInfo.title}>
					<span class="marquee-text">{trackInfo.title}</span>
				</p>
			{/key}
		</div>
	{:else}
		<p class="text-sm text-text-muted">{t('player.no_track')}</p>
	{/if}

	<!-- Progress bar -->
	<div class="w-full max-w-sm">
		{#if state.loading}
			<div class="w-full h-2 bg-surface-lighter rounded-full overflow-hidden">
				<div class="h-full w-1/3 bg-primary rounded-full animate-indeterminate"></div>
			</div>
			<div class="flex justify-center mt-1">
				<span class="text-xs text-text-muted">{t('player.loading')}</span>
			</div>
		{:else}
			<div
				role="slider"
				tabindex={canSeek ? 0 : -1}
				aria-label={t('player.seek')}
				aria-valuemin={0}
				aria-valuemax={Math.round(state.duration)}
				aria-valuenow={Math.round(state.elapsed)}
				aria-valuetext={`${formatTime(state.elapsed)} / ${formatTime(state.duration)}`}
				class="w-full h-2 bg-surface-lighter rounded-full relative {canSeek ? 'cursor-pointer' : 'cursor-default opacity-50'}"
				onclick={canSeek ? handleSeekClick : undefined}
				onpointerdown={canSeek ? handleSeekDragStart : undefined}
				onpointermove={canSeek ? handleSeekDragMove : undefined}
				onpointerup={canSeek ? handleSeekDragEnd : undefined}
				onkeydown={canSeek ? (e) => {
					const step = e.shiftKey ? 30 : 5;
					if (e.key === 'ArrowRight') { e.preventDefault(); player.seek(Math.min(state.duration, state.elapsed + step)); }
					else if (e.key === 'ArrowLeft') { e.preventDefault(); player.seek(Math.max(0, state.elapsed - step)); }
				} : undefined}
			>
				<div
					class="h-full bg-primary rounded-full pointer-events-none"
					style="width: {progress}%; transition: width {seekDragging ? '0s' : '1s'} linear"
				></div>
				{#if canSeek && (seekThumbVisible || seekDragging)}
					<div
						class="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-4 h-4 bg-primary rounded-full shadow transition-opacity duration-200 pointer-events-none"
						style="left: {progress}%"
					></div>
				{/if}
			</div>
			<div class="flex justify-between mt-1 text-xs text-text-muted">
				<span>{formatTime(state.elapsed)}</span>
			<span>{formatTime(state.duration)}</span>
		</div>
		{/if}
	</div>

	<!-- Controls -->
	<div class="flex items-center gap-4">
		<!-- Shuffle: only with multiple tracks in queue -->
		{#if hasQueue}
			<button
				onclick={toggleShuffle}
				class="p-2 transition-colors active:scale-95 {shuffleOn ? 'text-primary' : 'text-text-muted hover:text-text'}"
				aria-label={shuffleOn ? t('player.shuffle_off') : t('player.shuffle_on')}
			>
				<svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<polyline points="16 3 21 3 21 8"/>
					<line x1="4" y1="20" x2="21" y2="3"/>
					<polyline points="21 16 21 21 16 21"/>
					<line x1="15" y1="15" x2="21" y2="21"/>
					<line x1="4" y1="4" x2="9" y2="9"/>
				</svg>
			</button>
		{/if}

		<!-- Previous: hidden for live streams -->
		{#if !isLiveStream}
			<button
				onclick={() => player.previous()}
				disabled={state.playlist_position <= 0 && state.repeat_mode === 'off'}
				class="p-3 text-text-muted hover:text-text transition-colors active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed"
				aria-label={t('player.previous')}
			>
				<svg class="w-8 h-8" viewBox="0 0 24 24" fill="currentColor">
					<path d="M6 6h2v12H6zm3.5 6 8.5 6V6z"/>
				</svg>
			</button>
		{/if}

		<!-- Play/Pause -->
		<button
			onclick={handleToggle}
			disabled={!canPlay}
			class="p-5 bg-primary hover:bg-primary-light rounded-full text-white transition-colors active:scale-95 shadow-lg disabled:opacity-40 disabled:cursor-not-allowed"
			aria-label={isPlaying ? t('player.pause') : t('player.play')}
		>
			{#if isPlaying}
				<svg class="w-10 h-10" viewBox="0 0 24 24" fill="currentColor">
					<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
				</svg>
			{:else}
				<svg class="w-10 h-10" viewBox="0 0 24 24" fill="currentColor">
					<path d="M8 5v14l11-7z"/>
				</svg>
			{/if}
		</button>

		<!-- Next: hidden for live streams -->
		{#if !isLiveStream}
			<button
				onclick={() => player.next()}
				disabled={isLastTrack && state.repeat_mode === 'off'}
				class="p-3 text-text-muted hover:text-text transition-colors active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed"
				aria-label={t('player.next')}
			>
				<svg class="w-8 h-8" viewBox="0 0 24 24" fill="currentColor">
					<path d="M6 18l8.5-6L6 6zm10 0V6h2v12z"/>
				</svg>
			</button>
		{/if}

		<!-- Repeat: hidden for live streams, always available otherwise -->
		{#if !isLiveStream}
			<button
				onclick={() => player.repeat()}
				class="p-2 transition-colors active:scale-95 {state.repeat_mode !== 'off' ? 'text-primary' : 'text-text-muted hover:text-text'}"
				aria-label={t('player.repeat_aria')}
			>
				{#if state.repeat_mode === 'single'}
					<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
						<path d="M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z"/>
						<text x="12" y="15" text-anchor="middle" font-size="7" font-weight="bold">1</text>
					</svg>
				{:else if state.repeat_mode === 'all'}
					<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
						<path d="M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z"/>
					</svg>
				{:else}
					<svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<polyline points="17 1 21 5 17 9"/>
						<path d="M3 11V9a4 4 0 0 1 4-4h14"/>
						<polyline points="7 23 3 19 7 15"/>
						<path d="M21 13v2a4 4 0 0 1-4 4H3"/>
					</svg>
				{/if}
			</button>
		{/if}
	</div>


	<!-- Volume with mute -->
	<div class="w-full max-w-sm flex items-center gap-3">
		<button
			onclick={toggleMute}
			class="shrink-0 p-1 text-text-muted hover:text-text transition-colors"
			aria-label={muted ? t('player.unmute') : t('player.mute')}
		>
			{#if muted || localVolume === 0}
				<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
					<path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/>
				</svg>
			{:else if localVolume < 50}
				<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
					<path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/>
				</svg>
			{:else}
				<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
					<path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
				</svg>
			{/if}
		</button>
		<input
			type="range"
			min="0"
			max="100"
			bind:value={localVolume}
			onpointerdown={handleVolumeStart}
			onpointerup={handleVolumeEnd}
			onchange={handleVolumeEnd}
			class="w-full h-2 bg-surface-lighter rounded-full appearance-none cursor-pointer
				[&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:h-5
				[&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary"
			aria-label={t('player.volume')}
		/>
		<span class="text-xs text-text-muted w-8 text-right tabular-nums">{localVolume}</span>
	</div>

	<!-- Audio output toggle -->
	{#if outputs.length > 1}
		<div class="w-full max-w-sm flex justify-center">
			<button
				onclick={toggleBrowserAudio}
				disabled={browserLoading}
				class="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs transition-colors {browserPlaying ? 'bg-primary text-white' : 'bg-surface-light text-text-muted hover:text-text'} {browserLoading ? 'opacity-70' : ''}"
			>
				{#if browserLoading}
					<div class="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin"></div>
					{t('player.connecting')}
				{:else}
					<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						{#if browserPlaying}
							<rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>
							<line x1="12" y1="18" x2="12" y2="18.01"/>
						{:else}
							<path d="M3 9v6h4l5 5V4L7 9H3z"/>
							<line x1="12" y1="9" x2="12" y2="15"/>
						{/if}
					</svg>
					{browserPlaying ? t('player.browser_audio_on') : t('player.browser_audio_off')}
				{/if}
			</button>
		</div>
	{/if}

</div>

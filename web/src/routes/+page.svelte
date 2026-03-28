<script lang="ts">
	import { t } from '$lib/i18n';
	import { player } from '$lib/api';
	import { getPlayerState } from '$lib/stores/player.svelte';
	import { formatTime, parseTrackName } from '$lib/utils';
	import { tick, onMount } from 'svelte';

	const state = $derived(getPlayerState());
	const isPlaying = $derived(state.state === 'playing');
	const hasTrack = $derived(state.current_track !== '');
	const isLastTrack = $derived(state.playlist_position >= state.playlist_length - 1);
	const canPlay = $derived(hasTrack || state.playlist_length > 0);
	const canSeek = $derived(!state.is_stream && state.duration > 0);
	const trackInfo = $derived(parseTrackName(state.current_track));

	let volumeChanging = $state(false);
	let localVolume = $state(50);
	let muted = $state(false);
	let outputs = $state<{ id: number; name: string; enabled: boolean }[]>([]);
	let browserAudio = $state<HTMLAudioElement | null>(null);
	let browserPlaying = $state(false);
	let premuteVolume = $state(50);
	let shuffleOn = $state(false);
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
		shuffleOn = !shuffleOn;
		player.shuffle();
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
			player.seek(ratio * state.duration).then(() => { seekOverride = false; });
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
		player.seek(ratio * state.duration).then(() => { seekOverride = false; });
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

	onMount(async () => {
		try { outputs = await player.outputs(); } catch {}
	});

	async function toggleBrowserAudio() {
		const browserOut = outputs.find(o => o.name === 'Browser');
		if (!browserOut) return;
		if (browserPlaying) {
			// Turn off browser streaming
			await player.toggleOutput(browserOut.id, false);
			browserAudio?.pause();
			browserPlaying = false;
		} else {
			// Turn on browser streaming
			await player.toggleOutput(browserOut.id, true);
			if (browserAudio) {
				browserAudio.src = `/api/player/stream`;
				browserAudio.load();
				browserAudio.play().catch(() => {});
			}
			browserPlaying = true;
		}
		outputs = await player.outputs();
	}

	function handleToggle() {
		if (state.state === 'stopped' && state.playlist_length > 0) {
			player.play();
		} else {
			player.toggle();
		}
	}
</script>

<div class="flex flex-col items-center justify-center h-full px-6 py-8 gap-6">
	<!-- Cover Art -->
	<div class="w-64 h-64 sm:w-72 sm:h-72 rounded-2xl bg-surface-light flex items-center justify-center shadow-xl overflow-hidden">
		{#if hasTrack}
			<svg class="w-24 h-24 text-primary opacity-40" viewBox="0 0 24 24" fill="currentColor">
				<path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55C7.79 13 6 14.79 6 17s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
			</svg>
		{:else}
			<svg class="w-20 h-20 text-text-muted opacity-30" viewBox="0 0 24 24" fill="currentColor">
				<path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55C7.79 13 6 14.79 6 17s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
			</svg>
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
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="w-full h-2 bg-surface-lighter rounded-full relative {canSeek ? 'cursor-pointer' : 'cursor-default opacity-50'}"
			onclick={canSeek ? handleSeekClick : undefined}
			onpointerdown={canSeek ? handleSeekDragStart : undefined}
			onpointermove={canSeek ? handleSeekDragMove : undefined}
			onpointerup={canSeek ? handleSeekDragEnd : undefined}
		>
			<div
				class="h-full bg-primary rounded-full pointer-events-none"
				style="width: {progress}%"
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
	</div>

	<!-- Controls -->
	<div class="flex items-center gap-4">
		<!-- Shuffle -->
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

		<!-- Previous -->
		<button
			onclick={() => player.previous()}
			class="p-3 text-text-muted hover:text-text transition-colors active:scale-95"
			aria-label={t('player.previous')}
		>
			<svg class="w-8 h-8" viewBox="0 0 24 24" fill="currentColor">
				<path d="M6 6h2v12H6zm3.5 6 8.5 6V6z"/>
			</svg>
		</button>

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

		<!-- Next -->
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

		<!-- Repeat -->
		<button
			onclick={() => player.repeat()}
			class="p-2 transition-colors active:scale-95 {state.repeat_mode !== 'off' ? 'text-primary' : 'text-text-muted hover:text-text'}"
			aria-label="Wiederholung"
		>
			{#if state.repeat_mode === 'single'}
				<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
					<path d="M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z"/>
					<text x="12" y="15" text-anchor="middle" font-size="7" font-weight="bold">1</text>
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
				class="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs transition-colors {browserPlaying ? 'bg-primary text-white' : 'bg-surface-light text-text-muted hover:text-text'}"
			>
				<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					{#if browserPlaying}
						<rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>
						<line x1="12" y1="18" x2="12" y2="18.01"/>
					{:else}
						<path d="M3 9v6h4l5 5V4L7 9H3z"/>
						<line x1="12" y1="9" x2="12" y2="15"/>
					{/if}
				</svg>
				{browserPlaying ? 'Browser-Audio an' : 'Auf diesem Gerät hören'}
			</button>
		</div>
	{/if}

	<!-- Hidden audio element for browser streaming -->
	<audio bind:this={browserAudio} class="hidden"></audio>
</div>

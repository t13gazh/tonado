<script lang="ts">
	import { t } from '$lib/i18n';
	import { player } from '$lib/api';
	import { getPlayerState } from '$lib/stores/player.svelte';
	import { formatTime } from '$lib/utils';

	const state = $derived(getPlayerState());
	const isPlaying = $derived(state.state === 'playing');
	const hasTrack = $derived(state.current_track !== '');
	const progress = $derived(state.duration > 0 ? (state.elapsed / state.duration) * 100 : 0);

	let volumeChanging = $state(false);
	let localVolume = $state(50);
	let muted = $state(false);
	let premuteVolume = $state(50);
	let shuffleOn = $state(false);

	$effect(() => {
		if (!volumeChanging) {
			localVolume = state.volume;
		}
	});

	function handleVolumeStart() {
		volumeChanging = true;
	}

	function handleVolumeEnd() {
		volumeChanging = false;
		player.volume(localVolume);
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

	function handleSeek(e: MouseEvent) {
		const bar = e.currentTarget as HTMLElement;
		const rect = bar.getBoundingClientRect();
		const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
		player.seek(ratio * state.duration);
	}
</script>

<div class="flex flex-col items-center justify-center h-full px-6 py-8 gap-6">
	<!-- Cover Art -->
	<div class="w-64 h-64 sm:w-72 sm:h-72 rounded-2xl bg-surface-light flex items-center justify-center shadow-xl overflow-hidden">
		{#if hasTrack}
			<div class="flex flex-col items-center justify-center text-center p-4">
				<svg class="w-16 h-16 text-primary mb-4" viewBox="0 0 24 24" fill="currentColor">
					<path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55C7.79 13 6 14.79 6 17s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
				</svg>
				<p class="text-lg font-semibold text-text truncate max-w-full">{state.current_track}</p>
				{#if state.current_album}
					<p class="text-sm text-text-muted truncate max-w-full mt-1">{state.current_album}</p>
				{/if}
			</div>
		{:else}
			<div class="flex flex-col items-center text-text-muted">
				<svg class="w-20 h-20 mb-3 opacity-30" viewBox="0 0 24 24" fill="currentColor">
					<path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55C7.79 13 6 14.79 6 17s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
				</svg>
				<p class="text-sm">{t('player.no_track')}</p>
			</div>
		{/if}
	</div>

	<!-- Progress bar -->
	<div class="w-full max-w-sm">
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="w-full h-2 bg-surface-lighter rounded-full cursor-pointer relative"
			onclick={handleSeek}
		>
			<div
				class="h-full bg-primary rounded-full transition-[width] duration-200"
				style="width: {progress}%"
			></div>
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
			onclick={() => player.toggle()}
			class="p-5 bg-primary hover:bg-primary-light rounded-full text-white transition-colors active:scale-95 shadow-lg"
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
			class="p-3 text-text-muted hover:text-text transition-colors active:scale-95"
			aria-label={t('player.next')}
		>
			<svg class="w-8 h-8" viewBox="0 0 24 24" fill="currentColor">
				<path d="M6 18l8.5-6L6 6zm10 0V6h2v12z"/>
			</svg>
		</button>

		<!-- Mute placeholder for symmetry -->
		<div class="w-9"></div>
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
</div>

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
	<div class="flex items-center gap-6">
		<!-- Previous -->
		<button
			onclick={() => player.previous()}
			class="p-3 text-text-muted hover:text-text transition-colors active:scale-95"
			aria-label={t('player.previous')}
		>
			<svg class="w-8 h-8" viewBox="0 0 24 24" fill="currentColor">
				<path d="M6 6h2v12H6V6zm3.5 6 8.5 6V6l-8.5 6z"/>
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
				<path d="M6 18l8.5-6L6 6v12zm2 0V6l6.5 6L8 18zm8-12v12h2V6h-2z"/>
			</svg>
		</button>
	</div>

	<!-- Volume -->
	<div class="w-full max-w-sm flex items-center gap-3">
		<svg class="w-5 h-5 text-text-muted shrink-0" viewBox="0 0 24 24" fill="currentColor">
			<path d="M3 9v6h4l5 5V4L7 9H3z"/>
		</svg>
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

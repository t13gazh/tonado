<script lang="ts">
	import { t } from '$lib/i18n';
	import { streams, player, type RadioStation } from '$lib/api';
	import { getPlayerState } from '$lib/stores/player.svelte';
	import { goto } from '$app/navigation';
	import type { Snippet } from 'svelte';

	interface Props {
		stations: RadioStation[];
		onError: (msg: string) => void;
		onReloadRadio: () => Promise<void>;
		playCircle: Snippet<[onclick: () => void, disabled?: boolean, nowActive?: boolean]>;
		thumbnail: Snippet<[src: string | null, fallbackIcon: string]>;
		chevron: Snippet<[expanded: boolean, onclick: () => void]>;
	}

	let { stations, onError, onReloadRadio, playCircle, thumbnail, chevron }: Props = $props();

	const playerState = $derived(getPlayerState());
	const nowPlayingUri = $derived(playerState.current_uri);
	const isPlaying = $derived(playerState.state === 'playing');

	let showAddStation = $state(false);
	let newStationName = $state('');
	let newStationUrl = $state('');
	let urlError = $state('');
	let expandedRadio = $state<number | null>(null);

	function isNowPlaying(path: string): boolean {
		return nowPlayingUri === path;
	}

	async function playContent(url: string) {
		try {
			if (isNowPlaying(url)) {
				await player.toggle();
				return;
			}
			await player.playUrl(url);
			goto('/');
		} catch { onError(t('general.error')); }
	}

	function isValidUrl(url: string): boolean {
		try { const u = new URL(url); return u.protocol === 'http:' || u.protocol === 'https:'; }
		catch { return false; }
	}

	async function addStation() {
		urlError = '';
		if (!newStationName.trim() || !newStationUrl.trim()) return;
		if (!isValidUrl(newStationUrl)) { urlError = t('content.radio_url_invalid'); return; }
		try {
			await streams.addRadio(newStationName.trim(), newStationUrl.trim());
			newStationName = ''; newStationUrl = ''; showAddStation = false;
			await onReloadRadio();
		} catch { onError(t('error.create_failed')); }
	}

	async function removeStation(id: number) {
		if (!confirm(t('general.confirm_delete'))) return;
		try {
			await streams.deleteRadio(id);
			expandedRadio = null;
			await onReloadRadio();
		} catch { onError(t('error.delete_failed')); }
	}
</script>

<div class="flex justify-end mb-3">
	{#if showAddStation}
		<button onclick={() => { showAddStation = false; urlError = ''; }} class="text-sm text-text-muted">{t('content.close_form')}</button>
	{:else}
		<button onclick={() => (showAddStation = true)} class="text-sm text-primary font-medium">+ {t('content.radio_add')}</button>
	{/if}
</div>
{#if showAddStation}
	<div class="flex flex-col gap-2 mb-4 p-3 bg-surface-light rounded-xl">
		<input type="text" bind:value={newStationName} placeholder={t('content.radio_name')} class="px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary" />
		<input type="url" bind:value={newStationUrl} placeholder={t('content.radio_url')} class="px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary {urlError ? 'border-red-500' : ''}" />
		{#if urlError}<p class="text-xs text-red-400">{urlError}</p>{/if}
		<button onclick={addStation} class="px-4 py-2 bg-primary text-white rounded-lg text-sm self-end">{t('general.save')}</button>
	</div>
{/if}
{#if stations.length === 0}
	<div class="text-center py-12 text-text-muted text-sm">{t('library.no_stations')}</div>
{:else}
	<div class="flex flex-col gap-2">
		{#each stations as station (station.id)}
			{@const expanded = expandedRadio === station.id}
			<div class="bg-surface-light rounded-xl overflow-hidden">
				<div class="flex items-center gap-2.5 p-3">
					{@render playCircle(() => playContent(station.url), false, isNowPlaying(station.url))}
					{@render thumbnail(station.logo_url, 'radio')}
					<button onclick={() => (expandedRadio = expanded ? null : station.id)} class="flex-1 min-w-0 text-left">
						<p class="text-sm font-medium text-text truncate">{station.name}</p>
						<p class="text-xs text-text-muted">{station.category === 'kinder' ? t('library.station_kinder') : station.category === 'allgemein' ? t('library.station_general') : t('library.station_custom')}</p>
					</button>
					{@render chevron(expanded, () => (expandedRadio = expanded ? null : station.id))}
				</div>
				{#if expanded}
					<div class="px-3 pb-3 border-t border-surface-lighter">
						<p class="text-[10px] text-text-muted font-mono py-2 truncate">{station.url}</p>
						<button onclick={() => removeStation(station.id)} class="text-xs text-red-400 hover:text-red-300">{t('library.delete_station')}</button>
					</div>
				{/if}
			</div>
		{/each}
	</div>
{/if}

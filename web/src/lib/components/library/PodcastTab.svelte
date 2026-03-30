<script lang="ts">
	import { t } from '$lib/i18n';
	import { streams, player, type PodcastInfo } from '$lib/api';
	import { getPlayerState } from '$lib/stores/player.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import { goto } from '$app/navigation';
	import type { Snippet } from 'svelte';

	interface Props {
		podcasts: PodcastInfo[];
		onError: (msg: string) => void;
		onReloadPodcasts: () => Promise<void>;
		playCircle: Snippet<[onclick: () => void, disabled?: boolean, nowActive?: boolean]>;
		thumbnail: Snippet<[src: string | null, fallbackIcon: string]>;
		chevron: Snippet<[expanded: boolean, onclick: () => void]>;
	}

	let { podcasts, onError, onReloadPodcasts, playCircle, thumbnail, chevron }: Props = $props();

	const playerState = $derived(getPlayerState());
	const nowPlayingUri = $derived(playerState.current_uri);
	const isPlaying = $derived(playerState.state === 'playing');

	let showAddPodcast = $state(false);
	let newPodcastName = $state('');
	let newPodcastUrl = $state('');
	let urlError = $state('');
	let expandedPodcast = $state<number | null>(null);
	let podcastEpisodes = $state<{ title: string; audio_url: string; published: string | null }[]>([]);
	let loadingEpisodes = $state(false);

	function isNowPlaying(path: string): boolean {
		return nowPlayingUri === path;
	}

	function isValidUrl(url: string): boolean {
		try { const u = new URL(url); return u.protocol === 'http:' || u.protocol === 'https:'; }
		catch { return false; }
	}

	async function addPodcast() {
		urlError = '';
		if (!newPodcastName.trim() || !newPodcastUrl.trim()) return;
		if (!isValidUrl(newPodcastUrl)) { urlError = t('content.radio_url_invalid'); return; }
		try {
			await streams.addPodcast(newPodcastName.trim(), newPodcastUrl.trim());
			newPodcastName = ''; newPodcastUrl = ''; showAddPodcast = false;
			await onReloadPodcasts();
		} catch { onError(t('error.create_failed')); }
	}

	async function removePodcast(id: number) {
		if (!confirm(t('general.confirm_delete'))) return;
		try {
			await streams.deletePodcast(id);
			expandedPodcast = null; podcastEpisodes = [];
			await onReloadPodcasts();
		} catch { onError(t('error.delete_failed')); }
	}

	async function playPodcastEpisode(index: number) {
		if (podcastEpisodes.length === 0) return;
		const urls = podcastEpisodes.map(e => e.audio_url);
		try {
			await player.playUrls(urls, index);
			goto('/');
		} catch { onError(t('general.error')); }
	}

	async function togglePodcast(id: number) {
		if (expandedPodcast === id) { expandedPodcast = null; podcastEpisodes = []; return; }
		expandedPodcast = id; loadingEpisodes = true;
		try { podcastEpisodes = await streams.episodes(id); } catch { podcastEpisodes = []; }
		finally { loadingEpisodes = false; }
	}
</script>

<div class="flex justify-end mb-3">
	{#if showAddPodcast}
		<button onclick={() => { showAddPodcast = false; urlError = ''; }} class="text-sm text-text-muted">{t('content.close_form')}</button>
	{:else}
		<button onclick={() => (showAddPodcast = true)} class="text-sm text-primary font-medium">+ {t('content.podcast_add')}</button>
	{/if}
</div>
{#if showAddPodcast}
	<div class="flex flex-col gap-2 mb-4 p-3 bg-surface-light rounded-xl">
		<input type="text" bind:value={newPodcastName} placeholder={t('content.podcast_name')} class="px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary" />
		<input type="url" bind:value={newPodcastUrl} placeholder={t('content.podcast_url')} class="px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary {urlError ? 'border-red-500' : ''}" />
		{#if urlError}<p class="text-xs text-red-400">{urlError}</p>{/if}
		<button onclick={addPodcast} class="px-4 py-2 bg-primary text-white rounded-lg text-sm self-end">{t('general.save')}</button>
	</div>
{/if}
{#if podcasts.length === 0}
	<div class="text-center py-12 text-text-muted text-sm">{t('library.no_podcasts')}</div>
{:else}
	<div class="flex flex-col gap-2">
		{#each podcasts as podcast (podcast.id)}
			{@const expanded = expandedPodcast === podcast.id}
			<div class="bg-surface-light rounded-xl overflow-hidden">
				<div class="flex items-center gap-2.5 p-3">
					{@render playCircle(async () => {
						if (expandedPodcast !== podcast.id) await togglePodcast(podcast.id);
						if (podcastEpisodes.length > 0) await playPodcastEpisode(0);
					})}
					{@render thumbnail(podcast.logo_url, 'podcast')}
					<button onclick={() => togglePodcast(podcast.id)} class="flex-1 min-w-0 text-left">
						<p class="text-sm font-medium text-text truncate">{podcast.name}</p>
						<p class="text-xs text-text-muted">{t('library.episodes', { count: podcast.episode_count })}</p>
					</button>
					{@render chevron(expanded, () => togglePodcast(podcast.id))}
				</div>
				{#if expanded}
					<div class="px-3 pb-3 border-t border-surface-lighter">
						{#if loadingEpisodes}
							<div class="flex justify-center py-4"><Spinner size="sm" /></div>
						{:else if podcastEpisodes.length > 0}
							<div class="flex flex-col">
								{#each podcastEpisodes as ep, i}
									<button
										onclick={() => playPodcastEpisode(i)}
										class="flex items-center gap-2 py-2 text-left {i > 0 ? 'border-t border-surface-lighter/50' : ''}"
									>
										<span class="w-5 flex-shrink-0 flex items-center justify-center">
											{#if isNowPlaying(ep.audio_url) && isPlaying}
												<svg class="w-3.5 h-3.5 text-primary" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
											{:else}
												<svg class="w-3.5 h-3.5 text-text-muted" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
											{/if}
										</span>
										<span class="flex-1 min-w-0">
											<span class="text-xs block truncate {isNowPlaying(ep.audio_url) ? 'text-primary font-medium' : 'text-text'}">{ep.title}</span>
											{#if ep.published}
												<span class="text-[10px] text-text-muted">{new Date(ep.published).toLocaleDateString('de-DE')}</span>
											{/if}
										</span>
									</button>
								{/each}
							</div>
						{:else}
							<p class="text-xs text-text-muted py-2">{t('library.no_episodes')}</p>
						{/if}
						<div class="mt-2 pt-2 border-t border-surface-lighter">
							<button onclick={() => removePodcast(podcast.id)} class="text-xs text-red-400 hover:text-red-300">{t('library.delete_podcast')}</button>
						</div>
					</div>
				{/if}
			</div>
		{/each}
	</div>
{/if}

<script lang="ts">
	import { t } from '$lib/i18n';
	import { streams, player, type PodcastInfo } from '$lib/api';
	import { handleRadioKeydown } from '$lib/utils/radiogroup';
	import { getPlayerState } from '$lib/stores/player.svelte';
	import { canManageLibrary, isParentPinSet } from '$lib/stores/auth.svelte';
	import CoverArt from '$lib/components/CoverArt.svelte';
	import LoginSheet from '$lib/components/LoginSheet.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import { librarySearch, normalizeForSearch } from '$lib/stores/librarySearch.svelte';
	import { goto } from '$app/navigation';
	import type { Snippet } from 'svelte';

	interface Props {
		podcasts: PodcastInfo[];
		onError: (msg: string) => void;
		onReloadPodcasts: () => Promise<void>;
		playCircle: Snippet<[onclick: () => void, disabled?: boolean, nowActive?: boolean]>;
		chevron: Snippet<[expanded: boolean, onclick: () => void]>;
	}

	// Thumbnail snippet was dropped when CoverArt replaced the generic icon
	// placeholders (commit de38552). Only FolderTab still renders a thumbnail.
	let { podcasts, onError, onReloadPodcasts, playCircle, chevron }: Props = $props();

	// Sort mode (persisted). Podcasts have no added_at column; id DESC is a
	// stable proxy for "newly added". "episodes" = descending episode count.
	type SortMode = 'alpha' | 'recent' | 'episodes';
	const SORT_STORAGE_KEY = 'tonado.library.podcast_sort';
	const VALID_SORT_MODES: readonly SortMode[] = ['alpha', 'recent', 'episodes'] as const;

	function loadSortMode(): SortMode {
		if (typeof localStorage === 'undefined') return 'alpha';
		const stored = localStorage.getItem(SORT_STORAGE_KEY);
		return VALID_SORT_MODES.includes(stored as SortMode) ? (stored as SortMode) : 'alpha';
	}

	let sortMode = $state<SortMode>(loadSortMode());
	let radioRefs = $state<Record<SortMode, HTMLButtonElement | null>>({
		alpha: null,
		recent: null,
		episodes: null,
	});

	function setSortMode(mode: SortMode): void {
		sortMode = mode;
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem(SORT_STORAGE_KEY, mode);
		}
	}

	function onRadioKeydown(event: KeyboardEvent, current: SortMode): void {
		handleRadioKeydown<SortMode>(event, {
			options: VALID_SORT_MODES,
			current,
			onChange: setSortMode,
			onFocus: (next) => radioRefs[next]?.focus(),
		});
	}

	// Shared library search — sticky bar on the page feeds this via librarySearch.
	const searchQuery = $derived(librarySearch.query);
	const normalizedQuery = $derived(normalizeForSearch(searchQuery.trim()));
	const isSearching = $derived(normalizedQuery.length > 0);

	// Filter by podcast name only — episode titles are loaded lazily on expand,
	// so including them would force an N×feed pre-fetch for every keystroke on
	// a Pi Zero W (same cost constraint as FolderTab documents).
	const sortedPodcasts = $derived.by(() => {
		const searched = isSearching
			? podcasts.filter((p) => normalizeForSearch(p.name).includes(normalizedQuery))
			: podcasts;
		const arr = [...searched];
		if (sortMode === 'recent') {
			arr.sort((a, b) => b.id - a.id);
		} else if (sortMode === 'episodes') {
			arr.sort((a, b) => (b.episode_count ?? 0) - (a.episode_count ?? 0));
		} else {
			arr.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
		}
		return arr;
	});

	const playerState = $derived(getPlayerState());
	const nowPlayingUri = $derived(playerState.current_uri);
	const isPlaying = $derived(playerState.state === 'playing');

	let showAddPodcast = $state(false);
	let newPodcastName = $state('');
	let newPodcastUrl = $state('');
	let urlError = $state('');
	let expandedPodcast = $state<number | null>(null);
	let podcastEpisodes = $state<{ title: string; audio_url: string; published: string | null; duration: string | null; image_url?: string | null }[]>([]);
	let loadingEpisodes = $state(false);

	// Login sheet state
	let loginSheetOpen = $state(false);
	let pendingAction = $state<(() => void | Promise<void>) | null>(null);

	function requireAuth(action: () => void | Promise<void>) {
		if (canManageLibrary() || !isParentPinSet()) {
			action();
			return;
		}
		pendingAction = action;
		loginSheetOpen = true;
	}

	function onLoginSuccess() {
		loginSheetOpen = false;
		if (pendingAction) {
			pendingAction();
			pendingAction = null;
		}
	}

	function onLoginClose() {
		loginSheetOpen = false;
		pendingAction = null;
	}

	function formatDate(dateStr: string): string {
		const d = new Date(dateStr);
		if (isNaN(d.getTime())) return dateStr;
		return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
	}

	function formatDuration(dur: string | null): string | null {
		if (!dur) return null;
		// Already "HH:MM:SS" or "MM:SS"
		if (dur.includes(':')) {
			const parts = dur.split(':').map(Number);
			if (parts.length === 3) {
				const [h, m] = parts;
				return h > 0 ? t('general.duration_hours', { h, m }) : t('general.duration_minutes', { m });
			}
			return t('general.duration_minutes', { m: parts[0] });
		}
		// Seconds as string
		const sec = parseInt(dur, 10);
		if (isNaN(sec)) return null;
		const m = Math.floor(sec / 60);
		const h = Math.floor(m / 60);
		return h > 0 ? t('general.duration_hours', { h, m: m % 60 }) : t('general.duration_minutes', { m });
	}

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

<div class="flex items-center justify-between gap-2 mb-3">
	<div role="radiogroup" aria-label={t('library.sort_label')} class="grid grid-cols-3 flex-1 rounded-lg bg-surface-light p-0.5">
		{#each [{ id: 'alpha', label: t('library.sort_alpha') }, { id: 'recent', label: t('library.sort_recent') }, { id: 'episodes', label: t('library.sort_episodes') }] as opt (opt.id)}
			{@const active = sortMode === opt.id}
			<button
				bind:this={radioRefs[opt.id as SortMode]}
				type="button"
				role="radio"
				aria-checked={active}
				tabindex={active ? 0 : -1}
				onclick={() => setSortMode(opt.id as SortMode)}
				onkeydown={(e) => onRadioKeydown(e, opt.id as SortMode)}
				class="min-h-11 px-3 rounded-md text-xs font-medium transition-colors text-center {active ? 'bg-primary text-white' : 'text-text-muted hover:text-text'}"
			>
				{opt.label}
			</button>
		{/each}
	</div>
	{#if showAddPodcast}
		<button onclick={() => { showAddPodcast = false; urlError = ''; }} class="text-sm text-text-muted">{t('content.close_form')}</button>
	{:else}
		<button onclick={() => requireAuth(() => { showAddPodcast = true; })} class="text-sm text-primary font-medium">+ {t('content.podcast_add')}</button>
	{/if}
</div>
{#if showAddPodcast}
	<div class="flex flex-col gap-2 mb-4 p-3 bg-surface-light rounded-xl">
		<input type="text" bind:value={newPodcastName} placeholder={t('content.podcast_name')} class="px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary" />
		<input type="url" bind:value={newPodcastUrl} placeholder={t('content.podcast_url')} class="px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary {urlError ? 'border-red-500' : ''}" />
		{#if urlError}<p class="text-xs text-red-400">{urlError}</p>{/if}
		<button onclick={() => requireAuth(addPodcast)} class="px-4 py-2 bg-primary text-white rounded-lg text-sm self-end">{t('general.save')}</button>
	</div>
{/if}
{#if podcasts.length === 0}
	<div class="text-center py-12 text-text-muted text-sm">{t('library.no_podcasts')}</div>
{:else if sortedPodcasts.length === 0}
	<!-- Search filtered out every podcast; distinct from the "no podcasts at all" state. -->
	<div class="text-center py-12 text-text-muted">
		<p class="text-sm">{t('library.search_no_results', { query: searchQuery })}</p>
	</div>
{:else}
	<div class="flex flex-col gap-2">
		{#each sortedPodcasts as podcast (podcast.id)}
			{@const expanded = expandedPodcast === podcast.id}
			<div class="bg-surface-light rounded-xl overflow-hidden">
				<div class="flex items-center gap-2.5 p-3">
					{@render playCircle(async () => {
						if (expandedPodcast !== podcast.id) await togglePodcast(podcast.id);
						if (podcastEpisodes.length > 0) await playPodcastEpisode(0);
					})}
					<!--
					  Podcast show cover: backend exposes `logo_url` (nullable).
					  CoverArt falls back to the gradient + initial when the URL
					  errors or is absent.
					-->
					<div class="w-10 h-10 flex-shrink-0">
						<CoverArt src={podcast.logo_url ?? undefined} title={podcast.name} size="sm" />
					</div>
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
										class="flex items-center gap-2 py-2 text-left min-h-[44px] {i > 0 ? 'border-t border-surface-lighter/50' : ''}"
									>
										<span class="w-5 flex-shrink-0 flex items-center justify-center">
											{#if isNowPlaying(ep.audio_url) && isPlaying}
												<svg class="w-3.5 h-3.5 text-primary" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
											{:else}
												<svg class="w-3.5 h-3.5 text-text-muted" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
											{/if}
										</span>
										<!--
										  Episode row cover: prefer the episode-specific
										  `<itunes:image>` if the feed provided one, otherwise
										  fall back to the show's `logo_url`. CoverArt handles
										  its own gradient-initial fallback when both are missing
										  or error out.
										-->
										<div class="w-8 h-8 flex-shrink-0">
											<CoverArt src={ep.image_url ?? podcast.logo_url ?? undefined} title={ep.title} size="sm" />
										</div>
										<span class="flex-1 min-w-0">
											<span class="text-xs block truncate {isNowPlaying(ep.audio_url) ? 'text-primary font-medium' : 'text-text'}">{ep.title}</span>
											<span class="text-[10px] text-text-muted">
												{#if ep.published}{formatDate(ep.published)}{/if}{#if ep.published && formatDuration(ep.duration)}{' · '}{/if}{#if formatDuration(ep.duration)}{formatDuration(ep.duration)}{/if}
											</span>
										</span>
									</button>
								{/each}
							</div>
						{:else}
							<p class="text-xs text-text-muted py-2">{t('library.no_episodes')}</p>
						{/if}
						<div class="mt-2 pt-2 border-t border-surface-lighter">
							<button onclick={() => requireAuth(() => removePodcast(podcast.id))} class="text-xs text-red-400 hover:text-red-300">{t('library.delete_podcast')}</button>
						</div>
					</div>
				{/if}
			</div>
		{/each}
	</div>
{/if}

<LoginSheet open={loginSheetOpen} onSuccess={onLoginSuccess} onClose={onLoginClose} />

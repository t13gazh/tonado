<script lang="ts">
	import { t } from '$lib/i18n';
	import { library, streams, playlistsApi, type MediaFolder, type RadioStation, type PodcastInfo, type PlaylistSummary } from '$lib/api';
	import { getPlayerState } from '$lib/stores/player.svelte';
	import { isBackendOffline, isStorageCritical, isStorageLow, getHealth } from '$lib/stores/health.svelte';
	import HealthBanner from '$lib/components/HealthBanner.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import FolderTab from '$lib/components/library/FolderTab.svelte';
	import RadioTab from '$lib/components/library/RadioTab.svelte';
	import PodcastTab from '$lib/components/library/PodcastTab.svelte';
	import PlaylistTab from '$lib/components/library/PlaylistTab.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import { onMount } from 'svelte';

	const playerState = $derived(getPlayerState());
	const isPlaying = $derived(playerState.state === 'playing');

	type Tab = 'folders' | 'radio' | 'podcasts' | 'playlists';
	let tab = $state<Tab>('folders');
	let error = $state('');

	$effect(() => {
		if (error) {
			const timer = setTimeout(() => (error = ''), 5000);
			return () => clearTimeout(timer);
		}
	});

	// Data loaded at page level, passed to tabs
	let folders = $state<MediaFolder[]>([]);
	let stations = $state<RadioStation[]>([]);
	let podcasts = $state<PodcastInfo[]>([]);
	let allPlaylists = $state<PlaylistSummary[]>([]);
	let loadingFolders = $state(true);
	let loadingRadio = $state(true);
	let loadingPodcasts = $state(true);
	let loadingPlaylists = $state(true);

	onMount(() => { loadFolders(); loadRadio(); loadPodcasts(); loadPlaylists(); });

	function setError(e: unknown) { if (!isBackendOffline()) error = e instanceof Error ? e.message : String(e); }
	function onError(msg: string) { error = msg; }
	async function loadFolders() { loadingFolders = true; try { folders = await library.folders(); } catch (e) { setError(e); } finally { loadingFolders = false; } }
	async function loadRadio() { loadingRadio = true; try { stations = await streams.listRadio(); } catch (e) { setError(e); } finally { loadingRadio = false; } }
	async function loadPodcasts() { loadingPodcasts = true; try { podcasts = await streams.listPodcasts(); } catch (e) { setError(e); } finally { loadingPodcasts = false; } }
	async function loadPlaylists() { loadingPlaylists = true; try { allPlaylists = await playlistsApi.list(); } catch (e) { setError(e); } finally { loadingPlaylists = false; } }
</script>

<!--
  UNIFIED ROW PATTERN (shared snippets passed to tabs):
  [ play circle ]  [ thumb ]  Title + Subtitle + Duration  [ chevron ]
-->

{#snippet playCircle(onclick: () => void, disabled?: boolean, nowActive?: boolean)}
	{@const showPause = nowActive && isPlaying}
	<button {onclick} class="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 transition-colors {disabled ? 'opacity-30' : ''} {showPause ? 'bg-primary text-white' : nowActive ? 'bg-primary/20 text-primary' : 'bg-primary/10 hover:bg-primary/20 text-primary'}" {disabled} aria-label={showPause ? t('player.pause_aria') : t('player.play_aria')}>
		{#if showPause}
			<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
		{:else}
			<svg class="w-5 h-5 ml-0.5" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
		{/if}
	</button>
{/snippet}

{#snippet thumbnail(src: string | null, fallbackIcon: string)}
	<div class="w-10 h-10 rounded-lg bg-surface-lighter flex-shrink-0 overflow-hidden flex items-center justify-center">
		{#if src}
			<img {src} alt="" class="w-full h-full object-cover" />
		{:else if fallbackIcon === 'folder'}
			<svg class="w-5 h-5 text-text-muted opacity-30" viewBox="0 0 24 24" fill="currentColor"><path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>
		{:else if fallbackIcon === 'radio'}
			<svg class="w-5 h-5 text-accent opacity-50" viewBox="0 0 24 24" fill="currentColor"><path d="M3.24 6.15C2.51 6.43 2 7.17 2 8v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8c0-.83-.47-1.57-1.24-1.85L12 2 3.24 6.15zM12 16a3 3 0 1 1 0-6 3 3 0 0 1 0 6z"/></svg>
		{:else if fallbackIcon === 'podcast'}
			<svg class="w-5 h-5 text-accent opacity-50" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C8.69 2 6 4.69 6 8s2.69 6 6 6 6-2.69 6-6-2.69-6-6-6zm0 10c-2.21 0-4-1.79-4-4s1.79-4 4-4 4 1.79 4 4-1.79 4-4 4zm-1.5 6.5v3h3v-3h-3z"/></svg>
		{:else}
			<svg class="w-5 h-5 text-primary opacity-50" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/></svg>
		{/if}
	</div>
{/snippet}

{#snippet chevron(expanded: boolean, onclick: () => void)}
	<button {onclick} class="p-1">
		<svg class="w-4 h-4 text-text-muted transition-transform {expanded ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
	</button>
{/snippet}

<div class="p-4">
	<h1 class="text-xl font-bold mb-4">{t('library.title')}</h1>

	{#if isStorageCritical()}
		<div class="mb-4"><HealthBanner type="error" message={t('health.storage_critical')} /></div>
	{:else if isStorageLow()}
		<div class="mb-4"><HealthBanner type="warning" message={t('health.storage_low', { free_mb: getHealth()?.storage.free_mb ?? 0 })} /></div>
	{/if}

	<div class="flex gap-2 mb-4 overflow-x-auto">
		{#each [['folders', t('content.tab_folders')], ['radio', t('content.tab_radio')], ['podcasts', t('content.tab_podcasts')], ['playlists', t('content.tab_playlists')]] as [key, label]}
			<button onclick={() => (tab = key as Tab)}
				class="px-3 py-1.5 text-xs font-medium rounded-full whitespace-nowrap transition-colors {tab === key ? 'bg-primary text-white' : 'bg-surface-light text-text-muted hover:text-text'}"
			>{label}</button>
		{/each}
	</div>

	{#if error}
		<div class="text-sm text-red-400 mb-3 p-3 bg-red-400/10 rounded-lg flex items-center justify-between">
			<span>{error}</span>
			<button onclick={() => (error = '')} class="text-red-400 hover:text-red-300 ml-2">
				<Icon name="x" size={16} />
			</button>
		</div>
	{/if}

	{#if tab === 'folders'}
		{#if loadingFolders}
			<div class="flex justify-center py-12"><Spinner /></div>
		{:else}
			<FolderTab {folders} {onError} onReloadFolders={loadFolders} {playCircle} {thumbnail} {chevron} />
		{/if}
	{:else if tab === 'radio'}
		{#if loadingRadio}
			<div class="flex justify-center py-12"><Spinner /></div>
		{:else}
			<!-- `thumbnail` not forwarded: radio rows render CoverArt directly. -->
			<RadioTab {stations} {onError} onReloadRadio={loadRadio} {playCircle} {chevron} />
		{/if}
	{:else if tab === 'podcasts'}
		{#if loadingPodcasts}
			<div class="flex justify-center py-12"><Spinner /></div>
		{:else}
			<!-- `thumbnail` not forwarded: podcast rows render CoverArt directly. -->
			<PodcastTab {podcasts} {onError} onReloadPodcasts={loadPodcasts} {playCircle} {chevron} />
		{/if}
	{:else if tab === 'playlists'}
		{#if loadingPlaylists}
			<div class="flex justify-center py-12"><Spinner /></div>
		{:else}
			<!-- `thumbnail` not forwarded: playlist rows render CoverArt directly. -->
			<PlaylistTab {allPlaylists} {folders} {onError} onReloadPlaylists={loadPlaylists} {playCircle} {chevron} />
		{/if}
	{/if}
</div>

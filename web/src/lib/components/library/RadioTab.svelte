<script lang="ts">
	import { t } from '$lib/i18n';
	import { streams, player, type RadioStation } from '$lib/api';
	import { handleRadioKeydown } from '$lib/utils/radiogroup';
	import { getPlayerState } from '$lib/stores/player.svelte';
	import { canManageLibrary, isParentPinSet } from '$lib/stores/auth.svelte';
	import CoverArt from '$lib/components/CoverArt.svelte';
	import LoginSheet from '$lib/components/LoginSheet.svelte';
	import { librarySearch, normalizeForSearch } from '$lib/stores/librarySearch.svelte';
	import { goto } from '$app/navigation';
	import type { Snippet } from 'svelte';

	interface Props {
		stations: RadioStation[];
		onError: (msg: string) => void;
		onReloadRadio: () => Promise<void>;
		playCircle: Snippet<[onclick: () => void, disabled?: boolean, nowActive?: boolean]>;
		chevron: Snippet<[expanded: boolean, onclick: () => void]>;
	}

	// Thumbnail snippet was dropped when CoverArt replaced the generic icon
	// placeholders (commit de38552). Only FolderTab still renders a thumbnail.
	let { stations, onError, onReloadRadio, playCircle, chevron }: Props = $props();

	// Sort mode (persisted). Radio has no created_at column; use id DESC as
	// a proxy for "newest first" (AUTOINCREMENT is monotonic). Only two options
	// — no duration or episode count makes sense for live streams.
	type SortMode = 'alpha' | 'recent';
	const SORT_STORAGE_KEY = 'tonado.library.radio_sort';
	const VALID_SORT_MODES: readonly SortMode[] = ['alpha', 'recent'] as const;

	function loadSortMode(): SortMode {
		if (typeof localStorage === 'undefined') return 'alpha';
		const stored = localStorage.getItem(SORT_STORAGE_KEY);
		return VALID_SORT_MODES.includes(stored as SortMode) ? (stored as SortMode) : 'alpha';
	}

	let sortMode = $state<SortMode>(loadSortMode());
	let radioRefs = $state<Record<SortMode, HTMLButtonElement | null>>({
		alpha: null,
		recent: null,
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

	// Filter first (by station name — the only meaningful field for a radio row),
	// then sort. Station URLs deliberately do not participate in search: they
	// are technical identifiers the user never types / expects to match against.
	const sortedStations = $derived.by(() => {
		const filtered = isSearching
			? stations.filter((s) => normalizeForSearch(s.name).includes(normalizedQuery))
			: stations;
		const arr = [...filtered];
		if (sortMode === 'recent') {
			arr.sort((a, b) => b.id - a.id);
		} else {
			arr.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
		}
		return arr;
	});

	const playerState = $derived(getPlayerState());
	const nowPlayingUri = $derived(playerState.current_uri);
	const isPlaying = $derived(playerState.state === 'playing');

	let showAddStation = $state(false);
	let newStationName = $state('');
	let newStationUrl = $state('');
	let urlError = $state('');
	let expandedRadio = $state<number | null>(null);

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

<div class="flex items-center justify-between gap-2 mb-3">
	<div role="radiogroup" aria-label={t('library.sort_label')} class="grid grid-cols-2 flex-1 rounded-lg bg-surface-light p-0.5">
		{#each [{ id: 'alpha', label: t('library.sort_alpha') }, { id: 'recent', label: t('library.sort_recent') }] as opt (opt.id)}
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
	{#if showAddStation}
		<button onclick={() => { showAddStation = false; urlError = ''; }} class="text-sm text-text-muted">{t('content.close_form')}</button>
	{:else}
		<button onclick={() => requireAuth(() => { showAddStation = true; })} class="text-sm text-primary font-medium">+ {t('content.radio_add')}</button>
	{/if}
</div>
{#if showAddStation}
	<div class="flex flex-col gap-2 mb-4 p-3 bg-surface-light rounded-xl">
		<input type="text" bind:value={newStationName} placeholder={t('content.radio_name')} class="px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary" />
		<input type="url" bind:value={newStationUrl} placeholder={t('content.radio_url')} class="px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary {urlError ? 'border-red-500' : ''}" />
		{#if urlError}<p class="text-xs text-red-400">{urlError}</p>{/if}
		<button onclick={() => requireAuth(addStation)} class="px-4 py-2 bg-primary text-white rounded-lg text-sm self-end">{t('general.save')}</button>
	</div>
{/if}
{#if stations.length === 0}
	<div class="text-center py-12 text-text-muted text-sm">{t('library.no_stations')}</div>
{:else if sortedStations.length === 0}
	<!-- Empty state when a search query filters everything out; distinct from
	     the "no stations at all" state above. -->
	<div class="text-center py-12 text-text-muted">
		<p class="text-sm">{t('library.search_no_results', { query: searchQuery })}</p>
	</div>
{:else}
	<div class="flex flex-col gap-2">
		{#each sortedStations as station (station.id)}
			{@const expanded = expandedRadio === station.id}
			<div class="bg-surface-light rounded-xl overflow-hidden">
				<div class="flex items-center gap-2.5 p-3">
					{@render playCircle(() => playContent(station.url), false, isNowPlaying(station.url))}
					<!--
					  Radio station logo: `logo_url` is populated for preset stations
					  (kinder/allgemein catalog) and may be null for custom streams.
					  CoverArt falls back to gradient + initial for missing logos.
					  Audio-stream covers are never auto-generated — no endpoint call.
					-->
					<div class="w-10 h-10 flex-shrink-0">
						<CoverArt src={station.logo_url ?? undefined} title={station.name} size="sm" />
					</div>
					<button onclick={() => (expandedRadio = expanded ? null : station.id)} class="flex-1 min-w-0 text-left">
						<p class="text-sm font-medium text-text truncate">{station.name}</p>
						<p class="text-xs text-text-muted">{station.category === 'kinder' ? t('library.station_kinder') : station.category === 'allgemein' ? t('library.station_general') : t('library.station_custom')}</p>
					</button>
					{@render chevron(expanded, () => (expandedRadio = expanded ? null : station.id))}
				</div>
				{#if expanded}
					<div class="px-3 pb-3 border-t border-surface-lighter">
						<p class="text-[10px] text-text-muted font-mono py-2 truncate">{station.url}</p>
						<button onclick={() => requireAuth(() => removeStation(station.id))} class="text-xs text-red-400 hover:text-red-300">{t('library.delete_station')}</button>
					</div>
				{/if}
			</div>
		{/each}
	</div>
{/if}

<LoginSheet open={loginSheetOpen} onSuccess={onLoginSuccess} onClose={onLoginClose} />

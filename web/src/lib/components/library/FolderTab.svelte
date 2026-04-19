<script lang="ts">
	import { t } from '$lib/i18n';
	import { library, player, ApiError, type MediaFolder, type MediaTrack } from '$lib/api';
	import { formatDuration, parseTrackName } from '$lib/utils';
	import { handleRadioKeydown } from '$lib/utils/radiogroup';
	import { getPlayerState } from '$lib/stores/player.svelte';
	import { isStorageCritical } from '$lib/stores/health.svelte';
	import { canManageLibrary, isParentPinSet } from '$lib/stores/auth.svelte';
	import { addToast } from '$lib/stores/toast.svelte';
	import LoginSheet from '$lib/components/LoginSheet.svelte';
	import CoverArt from '$lib/components/CoverArt.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import SearchBar from '$lib/components/library/SearchBar.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import { goto } from '$app/navigation';
	import { tick } from 'svelte';
	import type { Snippet } from 'svelte';

	// Normalize for accent-insensitive, case-insensitive comparison.
	// ß → ss is handled separately since it's not a combining diacritic.
	function normalize(s: string): string {
		return s
			.toLowerCase()
			.normalize('NFD')
			.replace(/\p{Diacritic}/gu, '')
			.replace(/ß/g, 'ss');
	}

	interface Props {
		folders: MediaFolder[];
		onError: (msg: string) => void;
		onReloadFolders: () => Promise<void>;
		playCircle: Snippet<[onclick: () => void, disabled?: boolean, nowActive?: boolean]>;
		chevron: Snippet<[expanded: boolean, onclick: () => void]>;
	}

	// `thumbnail` snippet was retired: folders now render CoverArt directly so the
	// on-disk / embedded cover served by `GET /api/library/cover` can flow through
	// the same load/fallback pipeline as radio/podcast/playlist rows.
	let { folders, onError, onReloadFolders, playCircle, chevron }: Props = $props();

	// Sort mode (persisted in localStorage). Default: alphabetical — matches prior behaviour.
	type SortMode = 'alpha' | 'recent' | 'duration';
	const SORT_STORAGE_KEY = 'tonado.library.folder_sort';
	const VALID_SORT_MODES: SortMode[] = ['alpha', 'recent', 'duration'];

	function loadSortMode(): SortMode {
		if (typeof localStorage === 'undefined') return 'alpha';
		const stored = localStorage.getItem(SORT_STORAGE_KEY);
		return VALID_SORT_MODES.includes(stored as SortMode) ? (stored as SortMode) : 'alpha';
	}

	let sortMode = $state<SortMode>(loadSortMode());
	// Refs for roving tabindex — focus moves between radios via Arrow keys.
	let radioRefs = $state<Record<SortMode, HTMLButtonElement | null>>({
		alpha: null,
		recent: null,
		duration: null,
	});

	function setSortMode(mode: SortMode): void {
		sortMode = mode;
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem(SORT_STORAGE_KEY, mode);
		}
	}

	// Arrow-key navigation delegated to the shared radiogroup utility so behaviour
	// stays aligned with the sibling sort controls (RadioTab, PlaylistTab, PodcastTab).
	function onRadioKeydown(event: KeyboardEvent, current: SortMode): void {
		handleRadioKeydown<SortMode>(event, {
			options: VALID_SORT_MODES,
			current,
			onChange: setSortMode,
			onFocus: (next) => radioRefs[next]?.focus(),
		});
	}

	// Free-text search — not persisted, resets on navigation. Debounced in SearchBar.
	let searchQuery = $state('');
	const normalizedQuery = $derived(normalize(searchQuery.trim()));
	const isSearching = $derived(normalizedQuery.length > 0);

	// Lazy track cache per folder path for cross-folder track-name search.
	// Only populated while searching; cleared when query becomes empty again.
	let trackCache = $state<Record<string, MediaTrack[]>>({});
	let tracksLoaded = $state(false);

	$effect(() => {
		// Kick off a best-effort bulk fetch the first time the user starts typing.
		// Failure is silent — name-only search still works as fallback.
		if (isSearching && !tracksLoaded) {
			tracksLoaded = true;
			void loadAllTracks();
		}
		if (!isSearching) {
			// Free memory once the search is closed; next search reloads fresh.
			trackCache = {};
			tracksLoaded = false;
		}
	});

	// Bounded-concurrency helper — keeps the lazy track fetch from spawning one
	// request per folder in parallel. On a Pi Zero W with 200 folders that would
	// mean 200 open HTTP connections + 200 MPD lookups on the first keystroke,
	// which risks OOM and starves the event loop. A worker pool of 4 keeps the
	// total memory footprint bounded while staying fast enough for perceived
	// responsiveness (~50 folders/sec on a Pi 3B+).
	async function withConcurrency<T, R>(
		items: T[],
		limit: number,
		fn: (item: T) => Promise<R>,
	): Promise<(R | undefined)[]> {
		const results: (R | undefined)[] = new Array(items.length);
		let i = 0;
		const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
			while (true) {
				const idx = i++;
				if (idx >= items.length) break;
				try {
					results[idx] = await fn(items[idx]);
				} catch {
					results[idx] = undefined;
				}
			}
		});
		await Promise.all(workers);
		return results;
	}

	async function loadAllTracks() {
		const targets = folders.map((f) => f.path);
		const results = await withConcurrency(targets, 4, (p) => library.tracks(p));
		const next: Record<string, MediaTrack[]> = {};
		results.forEach((value, i) => {
			if (value !== undefined) next[targets[i]] = value;
		});
		trackCache = next;
	}

	// Classifies why a folder matches the query. `null` = no match. `'name'` =
	// the folder name itself matches (no hint needed — user sees it already).
	// `track` = name didn't match, but a track inside did — we surface the first
	// matching track as a hint so it's obvious why the folder was kept.
	function matchReason(
		folder: MediaFolder,
		q: string,
	): { kind: 'name' } | { kind: 'track'; title: string } | null {
		if (!q) return { kind: 'name' };
		if (normalize(folder.name).includes(q)) return { kind: 'name' };
		const tracks = trackCache[folder.path];
		if (!tracks) return null;
		const hit = tracks.find((tr) => normalize(parseTrackName(tr.filename).title).includes(q));
		if (!hit) return null;
		return { kind: 'track', title: parseTrackName(hit.filename).title };
	}

	// Derived view: filter first (if searching), then sort. Does not mutate the prop.
	const sortedFolders = $derived.by(() => {
		const filtered = isSearching
			? folders.filter((f) => matchReason(f, normalizedQuery) !== null)
			: folders;
		const arr = [...filtered];
		if (sortMode === 'recent') {
			// Newest first: highest mtime at the top. Undefined/0 falls to the end.
			arr.sort((a, b) => (b.mtime ?? 0) - (a.mtime ?? 0));
		} else if (sortMode === 'duration') {
			// Longest first — what the user likely cares about when scanning by time.
			arr.sort((a, b) => (b.duration_seconds ?? 0) - (a.duration_seconds ?? 0));
		} else {
			// Alphabetical, locale-aware, case-insensitive.
			arr.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
		}
		return arr;
	});

	const playerState = $derived(getPlayerState());
	const nowPlayingUri = $derived(playerState.current_uri);
	const isPlaying = $derived(playerState.state === 'playing');

	let showNewFolder = $state(false);
	let newFolderName = $state('');
	let expandedFolder = $state<string | null>(null);
	let folderTracks = $state<MediaTrack[]>([]);
	let uploadFolder = $state('');
	let uploadProgress = $state(0);
	let uploading = $state(false);
	let uploadCurrent = $state(0);
	let uploadTotal = $state(0);
	let fileInputs = $state<Record<string, HTMLInputElement | null>>({});

	// Rename state — mirrors the inline-edit pattern from PlaylistTab.
	let renamingPath = $state<string | null>(null);
	let renameValue = $state('');
	let renameInput = $state<HTMLInputElement | null>(null);

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

	function isNowPlaying(type: 'folder' | 'url', path: string): boolean {
		if (type === 'folder') return nowPlayingUri.startsWith(path);
		return nowPlayingUri === path;
	}

	async function playContent(path: string) {
		try {
			if (isNowPlaying('folder', path)) {
				await player.toggle();
				return;
			}
			await player.playFolder(path);
			goto('/');
		} catch { onError(t('general.error')); }
	}

	async function playFolderFromTrack(folderPath: string, startIndex: number) {
		try {
			await player.playFolder(folderPath, startIndex);
			goto('/');
		} catch { onError(t('general.error')); }
	}

	async function createFolder() {
		if (!newFolderName.trim()) return;
		try {
			await library.createFolder(newFolderName.trim());
			newFolderName = '';
			showNewFolder = false;
			await onReloadFolders();
		} catch { onError(t('error.create_failed')); }
	}

	async function deleteFolder(name: string) {
		if (!confirm(t('general.confirm_delete'))) return;
		try {
			await library.deleteFolder(name);
			if (expandedFolder === name) expandedFolder = null;
			await onReloadFolders();
		} catch { onError(t('error.delete_failed')); }
	}

	async function startRename(folder: MediaFolder) {
		renamingPath = folder.path;
		renameValue = folder.name;
		await tick();
		renameInput?.focus();
		renameInput?.select();
	}

	function cancelRename() {
		renamingPath = null;
		renameValue = '';
	}

	async function submitRename(folder: MediaFolder) {
		const trimmed = renameValue.trim();
		if (!trimmed) { onError(t('library.folder_name_required')); return; }
		if (trimmed === folder.name) { cancelRename(); return; }
		// Duplicate check (client-side; backend enforces too). Folder `path`
		// equals the folder name, so we compare against it case-insensitively.
		const duplicate = folders.some(
			(f) => f.path !== folder.path && f.name.trim().toLowerCase() === trimmed.toLowerCase(),
		);
		if (duplicate) { onError(t('library.folder_name_duplicate')); return; }
		// Simple client-side invalid-char guard — same character class the
		// backend rejects. Backend remains source of truth.
		if (/[\\/:\x00-\x1f\x7f<>:"|?*]/.test(trimmed)) {
			onError(t('library.folder_name_invalid'));
			return;
		}
		const oldPath = folder.path;
		try {
			await library.renameFolder(oldPath, trimmed);
			renamingPath = null;
			renameValue = '';
			if (expandedFolder === oldPath) expandedFolder = trimmed;
			await onReloadFolders();
			addToast(t('library.folder_renamed'), 'success');
		} catch (err) {
			if (err instanceof ApiError) {
				if (err.status === 409) onError(t('library.folder_name_duplicate'));
				else if (err.status === 400) onError(t('library.folder_name_invalid'));
				else onError(t('error.save_failed'));
			} else {
				onError(t('error.save_failed'));
			}
		}
	}

	function onRenameKeydown(e: KeyboardEvent, folder: MediaFolder) {
		if (e.key === 'Enter') { e.preventDefault(); requireAuth(() => submitRename(folder)); }
		else if (e.key === 'Escape') { e.preventDefault(); cancelRename(); }
	}

	async function toggleFolder(name: string) {
		if (expandedFolder === name) {
			expandedFolder = null;
			folderTracks = [];
		} else {
			expandedFolder = name;
			try { folderTracks = await library.tracks(name); }
			catch { onError(t('error.load_failed')); }
		}
	}

	async function handleFiles(folderName: string, files: FileList) {
		if (isStorageCritical()) { onError(t('health.storage_critical')); return; }
		uploadFolder = folderName; uploading = true;
		uploadTotal = files.length; uploadCurrent = 0;
		try {
			for (let i = 0; i < files.length; i++) {
				uploadCurrent = i + 1; uploadProgress = 0;
				await library.upload(folderName, files[i], (pct) => { uploadProgress = pct; });
			}
			await onReloadFolders();
			if (expandedFolder === folderName) folderTracks = await library.tracks(folderName);
		} catch (err) {
			if (err instanceof ApiError && err.status === 413) {
				onError(t('error.upload_too_large'));
			} else if (err instanceof ApiError && err.status === 403) {
				onError(t('error.upload_auth_required'));
			} else {
				onError(t('error.upload_failed'));
			}
		} finally {
			uploading = false; uploadFolder = '';
		}
	}
</script>

<!-- Free-text search sits above the sort control. Not persisted across sessions. -->
<SearchBar value={searchQuery} oninput={(v) => (searchQuery = v)} />

<div class="flex items-center justify-between gap-2 mb-3">
	<!--
		Segmented control for sort mode. Radiogroup semantics so keyboard
		and screen reader users understand "one of three". 44px tap target.
	-->
	<div role="radiogroup" aria-label={t('library.sort_label')} class="grid grid-cols-3 flex-1 rounded-lg bg-surface-light p-0.5">
		{#each [{ id: 'alpha', label: t('library.sort_alpha') }, { id: 'recent', label: t('library.sort_recent') }, { id: 'duration', label: t('library.sort_duration') }] as opt (opt.id)}
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
	{#if showNewFolder}
		<button onclick={() => (showNewFolder = false)} class="text-sm text-text-muted">{t('content.close_form')}</button>
	{:else}
		<button onclick={() => requireAuth(() => { showNewFolder = true; })} class="text-sm text-primary font-medium">+ {t('content.new_folder')}</button>
	{/if}
</div>
{#if showNewFolder}
	<div class="flex gap-2 mb-4 p-3 bg-surface-light rounded-xl">
		<input type="text" bind:value={newFolderName} placeholder={t('content.folder_name')} class="flex-1 px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary" onkeydown={(e) => e.key === 'Enter' && requireAuth(createFolder)} />
		<button onclick={() => requireAuth(createFolder)} class="px-4 py-2 bg-primary text-white rounded-lg text-sm">{t('general.save')}</button>
	</div>
{/if}
{#if folders.length === 0}
	<div class="text-center py-16 text-text-muted"><p class="text-sm">{t('library.empty')}</p><p class="text-xs mt-1">{t('library.empty_hint')}</p></div>
{:else if sortedFolders.length === 0}
	<div class="text-center py-12 text-text-muted">
		<p class="text-sm">{t('library.search_no_results', { query: searchQuery })}</p>
	</div>
{:else}
	<div class="flex flex-col gap-2">
		{#each sortedFolders as folder (folder.path)}
			{@const expanded = expandedFolder === folder.path}
			{@const reason = isSearching ? matchReason(folder, normalizedQuery) : null}
			<div class="bg-surface-light rounded-xl overflow-hidden">
				<div class="flex items-center gap-2.5 p-3">
					{@render playCircle(() => playContent(folder.path), folder.track_count === 0, isNowPlaying('folder', folder.path))}
					<!--
					  Folder cover: resolved by `GET /api/library/cover?path=…&kind=folder`,
					  which prefers an on-disk `cover.*` file and falls back to the first
					  embedded APIC/Picture tag. CoverArt handles 404/error via the
					  gradient + initial tile so folders without any art still render.
					-->
					<div class="w-10 h-10 flex-shrink-0">
						<CoverArt src={library.coverUrl(folder.path, 'folder')} title={folder.name} size="sm" />
					</div>
					<button onclick={() => toggleFolder(folder.path)} class="flex-1 min-w-0 text-left">
						<p class="text-sm font-medium text-text truncate">{folder.name}</p>
						<p class="text-xs text-text-muted">{t('content.tracks', { count: folder.track_count })}{folder.duration_seconds ? ` · ${formatDuration(folder.duration_seconds)}` : ''}</p>
						{#if reason && reason.kind === 'track'}
							<!-- Track-match surfaces why this folder is in the search result set. -->
							<p class="text-xs text-primary/80 truncate mt-0.5">{t('library.search_match_track', { track: reason.title })}</p>
						{/if}
					</button>
					{@render chevron(expanded, () => toggleFolder(folder.path))}
				</div>
				{#if expanded}
					{@const isRenaming = renamingPath === folder.path}
					<div class="px-3 pb-3 border-t border-surface-lighter">
							<div class="py-2">
								{#if isRenaming}
									<div class="flex flex-col gap-2 p-2 bg-surface rounded-lg">
										<label class="text-[10px] text-text-muted uppercase tracking-wider" for="folder-rename-{folder.path}">{t('library.folder_rename')}</label>
										<input
											id="folder-rename-{folder.path}"
											bind:this={renameInput}
											bind:value={renameValue}
											onkeydown={(e) => onRenameKeydown(e, folder)}
											type="text"
											maxlength="200"
											placeholder={t('content.folder_name')}
											class="px-3 py-2 bg-surface-light border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary"
										/>
										<div class="flex gap-2 justify-end">
											<button onclick={cancelRename} class="min-h-[44px] px-3 text-sm text-text-muted">{t('general.cancel')}</button>
											<button onclick={() => requireAuth(() => submitRename(folder))} disabled={!renameValue.trim()} class="min-h-[44px] px-4 bg-primary disabled:opacity-30 text-white rounded-lg text-sm">{t('general.save')}</button>
										</div>
									</div>
								{:else}
									<button onclick={() => requireAuth(() => startRename(folder))} class="flex items-center gap-1.5 text-xs text-text-muted hover:text-text min-h-[44px]">
										<Icon name="edit" size={14} />
										{t('library.folder_rename')}
									</button>
								{/if}
							</div>
							<div class="flex items-center gap-2 py-2">
								<button onclick={() => requireAuth(() => { fileInputs[folder.path]?.click(); })} class="flex items-center gap-1.5 px-3 py-1.5 bg-surface-lighter rounded-lg text-xs text-text-muted hover:text-text cursor-pointer">
									<svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/></svg>
									{t('library.upload')}
								</button>
								<input bind:this={fileInputs[folder.path]} type="file" multiple accept="audio/*,image/*" class="hidden" onchange={(e) => { const el = e.target as HTMLInputElement; if (el.files) handleFiles(folder.path, el.files); }} />
							</div>
						{#if uploading && uploadFolder === folder.path}
							{#if uploadTotal > 1}
								<p class="text-xs text-text-muted mb-1">{t('library.upload_progress', { current: uploadCurrent, total: uploadTotal })}</p>
							{/if}
							<div class="mb-2 h-1.5 bg-surface-lighter rounded-full overflow-hidden"><div class="h-full bg-primary transition-[width] duration-200" style="width: {uploadProgress}%"></div></div>
						{/if}
						{#if folderTracks.length > 0}
							<div class="flex flex-col">
								{#each folderTracks as track, i}
									<button
										onclick={() => playFolderFromTrack(folder.path, i)}
										class="flex items-center gap-2 py-1.5 text-xs w-full text-left hover:bg-surface-lighter/50 rounded transition-colors {i > 0 ? 'border-t border-surface-lighter/50' : ''}"
									>
										<span class="w-5 flex-shrink-0 flex items-center justify-center">
											{#if isNowPlaying('folder', track.path) && isPlaying}
												<svg class="w-3.5 h-3.5 text-primary" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
											{:else}
												<svg class="w-3.5 h-3.5 text-text-muted" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
											{/if}
										</span>
										<span class="flex-1 truncate {isNowPlaying('folder', track.path) ? 'text-primary font-medium' : 'text-text'}">{parseTrackName(track.filename).title}</span>
										<span class="text-text-muted tabular-nums shrink-0">{formatDuration(track.duration_seconds)}</span>
									</button>
								{/each}
							</div>
						{:else}
							<p class="text-xs text-text-muted py-2">{t('library.no_tracks')}</p>
						{/if}
						<div class="mt-2 pt-2 border-t border-surface-lighter">
								<button onclick={() => requireAuth(() => deleteFolder(folder.path))} class="text-xs text-red-400 hover:text-red-300">{t('library.delete_folder')}</button>
							</div>
					</div>
				{/if}
			</div>
		{/each}
	</div>
{/if}

<LoginSheet open={loginSheetOpen} onSuccess={onLoginSuccess} onClose={onLoginClose} />

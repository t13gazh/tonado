<script lang="ts">
	import { t } from '$lib/i18n';
	import { library, player, ApiError, type MediaFolder, type MediaTrack } from '$lib/api';
	import { formatDuration, parseTrackName } from '$lib/utils';
	import { getPlayerState } from '$lib/stores/player.svelte';
	import { isStorageCritical } from '$lib/stores/health.svelte';
	import { canManageLibrary, isParentPinSet } from '$lib/stores/auth.svelte';
	import LoginSheet from '$lib/components/LoginSheet.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import { goto } from '$app/navigation';
	import type { Snippet } from 'svelte';

	interface Props {
		folders: MediaFolder[];
		onError: (msg: string) => void;
		onReloadFolders: () => Promise<void>;
		playCircle: Snippet<[onclick: () => void, disabled?: boolean, nowActive?: boolean]>;
		thumbnail: Snippet<[src: string | null, fallbackIcon: string]>;
		chevron: Snippet<[expanded: boolean, onclick: () => void]>;
	}

	let { folders, onError, onReloadFolders, playCircle, thumbnail, chevron }: Props = $props();

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

	function setSortMode(mode: SortMode): void {
		sortMode = mode;
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem(SORT_STORAGE_KEY, mode);
		}
	}

	// Derived sorted view — does not mutate the prop array.
	const sortedFolders = $derived.by(() => {
		const arr = [...folders];
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

<div class="flex items-center justify-between gap-2 mb-3">
	<!--
		Segmented control for sort mode. Radiogroup semantics so keyboard
		and screen reader users understand "one of three". 44px tap target.
	-->
	<div role="radiogroup" aria-label={t('library.sort_label')} class="inline-flex rounded-lg bg-surface-light p-0.5">
		{#each [{ id: 'alpha', label: t('library.sort_alpha') }, { id: 'recent', label: t('library.sort_recent') }, { id: 'duration', label: t('library.sort_duration') }] as opt (opt.id)}
			{@const active = sortMode === opt.id}
			<button
				type="button"
				role="radio"
				aria-checked={active}
				onclick={() => setSortMode(opt.id as SortMode)}
				class="min-h-11 px-3 rounded-md text-xs font-medium transition-colors {active ? 'bg-primary text-white' : 'text-text-muted hover:text-text'}"
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
{:else}
	<div class="flex flex-col gap-2">
		{#each sortedFolders as folder (folder.path)}
			{@const expanded = expandedFolder === folder.path}
			<div class="bg-surface-light rounded-xl overflow-hidden">
				<div class="flex items-center gap-2.5 p-3">
					{@render playCircle(() => playContent(folder.path), folder.track_count === 0, isNowPlaying('folder', folder.path))}
					{@render thumbnail(folder.cover_path, 'folder')}
					<button onclick={() => toggleFolder(folder.path)} class="flex-1 min-w-0 text-left">
						<p class="text-sm font-medium text-text truncate">{folder.name}</p>
						<p class="text-xs text-text-muted">{t('content.tracks', { count: folder.track_count })}{folder.duration_seconds ? ` · ${formatDuration(folder.duration_seconds)}` : ''}</p>
					</button>
					{@render chevron(expanded, () => toggleFolder(folder.path))}
				</div>
				{#if expanded}
					<div class="px-3 pb-3 border-t border-surface-lighter">
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

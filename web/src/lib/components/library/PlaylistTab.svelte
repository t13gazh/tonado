<script lang="ts">
	import { t } from '$lib/i18n';
	import { playlistsApi, type MediaFolder, type PlaylistSummary, type PlaylistDetail } from '$lib/api';
	import { formatDuration, parseTrackName } from '$lib/utils';
	import { canManageLibrary, isParentPinSet } from '$lib/stores/auth.svelte';
	import { addToast } from '$lib/stores/toast.svelte';
	import LoginSheet from '$lib/components/LoginSheet.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import { goto } from '$app/navigation';
	import { tick } from 'svelte';
	import type { Snippet } from 'svelte';

	interface Props {
		allPlaylists: PlaylistSummary[];
		folders: MediaFolder[];
		onError: (msg: string) => void;
		onReloadPlaylists: () => Promise<void>;
		playCircle: Snippet<[onclick: () => void, disabled?: boolean, nowActive?: boolean]>;
		thumbnail: Snippet<[src: string | null, fallbackIcon: string]>;
		chevron: Snippet<[expanded: boolean, onclick: () => void]>;
	}

	let { allPlaylists, folders, onError, onReloadPlaylists, playCircle, thumbnail, chevron }: Props = $props();

	let showNewPlaylist = $state(false);
	let newPlaylistName = $state('');
	let expandedPlaylist = $state<PlaylistDetail | null>(null);
	let showAddItem = $state(false);
	let newItemPath = $state('');
	let newItemTitle = $state('');

	// Rename state
	let renamingId = $state<number | null>(null);
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

	async function createPlaylist() {
		if (!newPlaylistName.trim()) return;
		try {
			await playlistsApi.create(newPlaylistName.trim());
			newPlaylistName = ''; showNewPlaylist = false;
			await onReloadPlaylists();
		} catch { onError(t('error.create_failed')); }
	}

	async function removePlaylist(id: number) {
		if (!confirm(t('general.confirm_delete'))) return;
		try {
			await playlistsApi.delete(id);
			if (expandedPlaylist?.id === id) expandedPlaylist = null;
			await onReloadPlaylists();
		} catch { onError(t('error.delete_failed')); }
	}

	async function startRename(pl: PlaylistSummary) {
		renamingId = pl.id;
		renameValue = pl.name;
		await tick();
		renameInput?.focus();
		renameInput?.select();
	}

	function cancelRename() {
		renamingId = null;
		renameValue = '';
	}

	async function submitRename(pl: PlaylistSummary) {
		const trimmed = renameValue.trim();
		if (!trimmed) { onError(t('library.playlist_name_required')); return; }
		if (trimmed === pl.name) { cancelRename(); return; }
		// Duplicate check (client side; backend enforces too)
		if (allPlaylists.some(p => p.id !== pl.id && p.name.trim().toLowerCase() === trimmed.toLowerCase())) {
			onError(t('library.playlist_name_duplicate'));
			return;
		}
		const id = pl.id;
		try {
			await playlistsApi.rename(id, trimmed);
			renamingId = null;
			renameValue = '';
			if (expandedPlaylist?.id === id) {
				expandedPlaylist = { ...expandedPlaylist, name: trimmed };
			}
			await onReloadPlaylists();
			addToast(t('library.playlist_renamed'), 'success');
		} catch {
			onError(t('error.save_failed'));
		}
	}

	function onRenameKeydown(e: KeyboardEvent, pl: PlaylistSummary) {
		if (e.key === 'Enter') { e.preventDefault(); requireAuth(() => submitRename(pl)); }
		else if (e.key === 'Escape') { e.preventDefault(); cancelRename(); }
	}

	async function togglePlaylist(id: number) {
		if (expandedPlaylist?.id === id) { expandedPlaylist = null; }
		else { try { expandedPlaylist = await playlistsApi.get(id); } catch { onError(t('error.load_failed')); } }
	}

	async function addPlaylistItem() {
		if (!expandedPlaylist || !newItemPath.trim()) return;
		try {
			await playlistsApi.addItem(expandedPlaylist.id, 'folder', newItemPath.trim(), newItemTitle.trim() || undefined);
			newItemPath = ''; newItemTitle = ''; showAddItem = false;
			expandedPlaylist = await playlistsApi.get(expandedPlaylist.id);
			await onReloadPlaylists();
		} catch { onError(t('error.save_failed')); }
	}

	async function removePlaylistItem(itemId: number) {
		if (!expandedPlaylist) return;
		try {
			await playlistsApi.removeItem(itemId);
			expandedPlaylist = await playlistsApi.get(expandedPlaylist.id);
			await onReloadPlaylists();
		} catch { onError(t('error.delete_failed')); }
	}
</script>

<div class="flex justify-end mb-3">
	{#if showNewPlaylist}
		<button onclick={() => (showNewPlaylist = false)} class="text-sm text-text-muted">{t('content.close_form')}</button>
	{:else}
		<button onclick={() => requireAuth(() => { showNewPlaylist = true; })} class="text-sm text-primary font-medium">+ {t('content.playlist_new')}</button>
	{/if}
</div>
{#if showNewPlaylist}
	<div class="flex gap-2 mb-4 p-3 bg-surface-light rounded-xl">
		<input type="text" bind:value={newPlaylistName} placeholder={t('content.playlist_name')} class="flex-1 px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary" onkeydown={(e) => e.key === 'Enter' && requireAuth(createPlaylist)} />
		<button onclick={() => requireAuth(createPlaylist)} class="px-4 py-2 bg-primary text-white rounded-lg text-sm">{t('general.save')}</button>
	</div>
{/if}
{#if allPlaylists.length === 0}
	<div class="text-center py-12 text-text-muted text-sm">{t('content.playlist_empty')}</div>
{:else}
	<div class="flex flex-col gap-2">
		{#each allPlaylists as pl (pl.id)}
			{@const expanded = expandedPlaylist?.id === pl.id}
			{@const isRenaming = renamingId === pl.id}
			<div class="bg-surface-light rounded-xl overflow-hidden">
				<div class="flex items-center gap-2.5 p-3">
					{@render playCircle(async () => { await playlistsApi.play(pl.id); goto('/'); }, pl.item_count === 0)}
					{@render thumbnail(null, 'playlist')}
					<button onclick={() => togglePlaylist(pl.id)} class="flex-1 min-w-0 text-left">
						<p class="text-sm font-medium text-text truncate">{pl.name}</p>
						<p class="text-xs text-text-muted">{t('library.entries', { count: pl.item_count })}{pl.duration_seconds ? ` · ${formatDuration(pl.duration_seconds)}` : ''}</p>
					</button>
					{@render chevron(expanded, () => togglePlaylist(pl.id))}
				</div>
				{#if expanded}
					<div class="px-3 pb-3 border-t border-surface-lighter">
						<div class="py-2">
							{#if isRenaming}
								<div class="flex flex-col gap-2 p-2 bg-surface rounded-lg">
									<label class="text-[10px] text-text-muted uppercase tracking-wider" for="rename-input-{pl.id}">{t('library.playlist_rename')}</label>
									<input
										id="rename-input-{pl.id}"
										bind:this={renameInput}
										bind:value={renameValue}
										onkeydown={(e) => onRenameKeydown(e, pl)}
										type="text"
										maxlength="100"
										placeholder={t('content.playlist_name')}
										class="px-3 py-2 bg-surface-light border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary"
									/>
									<div class="flex gap-2 justify-end">
										<button onclick={cancelRename} class="min-h-[44px] px-3 text-sm text-text-muted">{t('general.cancel')}</button>
										<button onclick={() => requireAuth(() => submitRename(pl))} disabled={!renameValue.trim()} class="min-h-[44px] px-4 bg-primary disabled:opacity-30 text-white rounded-lg text-sm">{t('general.save')}</button>
									</div>
								</div>
							{:else}
								<button onclick={() => requireAuth(() => startRename(pl))} class="flex items-center gap-1.5 text-xs text-text-muted hover:text-text min-h-[44px]">
									<Icon name="edit" size={14} />
									{t('library.playlist_rename')}
								</button>
							{/if}
						</div>
						<div class="py-2">
							{#if showAddItem}
								<div class="flex flex-col gap-2 p-2 bg-surface rounded-lg">
									{#if folders.length > 0}
										<p class="text-[10px] text-text-muted uppercase tracking-wider">{t('library.select_folder')}</p>
										<div class="flex flex-wrap gap-1">
											{#each folders as f}
												<button onclick={() => { newItemPath = f.path; newItemTitle = f.name; }}
													class="px-2 py-1 rounded text-xs transition-colors {newItemPath === f.path ? 'bg-primary text-white' : 'bg-surface-lighter text-text-muted hover:text-text'}"
												>{f.name}</button>
											{/each}
										</div>
									{/if}
									<input type="text" bind:value={newItemPath} placeholder={t('library.manual_path')} class="px-2 py-1.5 bg-surface-light border border-surface-lighter rounded text-text text-xs focus:outline-none focus:border-primary" />
									<input type="text" bind:value={newItemTitle} placeholder={t('library.display_name_placeholder')} class="px-2 py-1.5 bg-surface-light border border-surface-lighter rounded text-text text-xs focus:outline-none focus:border-primary" />
									<div class="flex gap-2 justify-end">
										<button onclick={() => (showAddItem = false)} class="text-xs text-text-muted">{t('general.cancel')}</button>
										<button onclick={() => requireAuth(addPlaylistItem)} disabled={!newItemPath.trim()} class="px-3 py-1 bg-primary disabled:opacity-30 text-white rounded text-xs">{t('general.save')}</button>
									</div>
								</div>
							{:else}
								<button onclick={() => requireAuth(() => { showAddItem = true; })} class="text-xs text-primary font-medium">{t('library.add_entry')}</button>
							{/if}
						</div>
						{#if expandedPlaylist && expandedPlaylist.items.length > 0}
							<div class="flex flex-col">
								{#each expandedPlaylist.items as item, i}
									<div class="flex items-center gap-2 py-1.5 text-xs {i > 0 ? 'border-t border-surface-lighter/50' : ''}">
										<span class="w-5 text-text-muted text-right tabular-nums">{item.position}</span>
										<span class="flex-1 text-text truncate">{item.title || parseTrackName(item.content_path).title}</span>
										{#if item.duration_seconds}<span class="text-text-muted tabular-nums shrink-0">{formatDuration(item.duration_seconds)}</span>{/if}
										<button onclick={() => requireAuth(() => removePlaylistItem(item.id))} class="p-0.5 text-text-muted/40 hover:text-red-400">
											<Icon name="x" size={14} />
										</button>
									</div>
								{/each}
							</div>
						{:else}
							<p class="text-xs text-text-muted py-1">{t('library.no_entries')}</p>
						{/if}
						<div class="mt-2 pt-2 border-t border-surface-lighter">
							<button onclick={() => requireAuth(() => removePlaylist(pl.id))} class="text-xs text-red-400 hover:text-red-300">{t('library.delete_playlist')}</button>
						</div>
					</div>
				{/if}
			</div>
		{/each}
	</div>
{/if}

<LoginSheet open={loginSheetOpen} onSuccess={onLoginSuccess} onClose={onLoginClose} />

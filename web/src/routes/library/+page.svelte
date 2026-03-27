<script lang="ts">
	import { t } from '$lib/i18n';
	import { library, streams, playlistsApi, type MediaFolder, type RadioStation, type PodcastInfo, type PlaylistSummary, type PlaylistDetail } from '$lib/api';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	type Tab = 'folders' | 'radio' | 'podcasts' | 'playlists';
	let tab = $state<Tab>('folders');
	let error = $state('');

	// Folders
	let folders = $state<MediaFolder[]>([]);
	let loadingFolders = $state(true);
	let showNewFolder = $state(false);
	let newFolderName = $state('');
	let expandedFolder = $state<string | null>(null);
	let folderTracks = $state<{ filename: string; path: string }[]>([]);
	let uploadFolder = $state('');
	let uploadProgress = $state(0);
	let uploading = $state(false);

	// Radio
	let stations = $state<RadioStation[]>([]);
	let loadingRadio = $state(true);
	let showAddStation = $state(false);
	let newStationName = $state('');
	let newStationUrl = $state('');
	let urlError = $state('');
	let expandedRadio = $state<number | null>(null);

	// Podcasts
	let podcasts = $state<PodcastInfo[]>([]);
	let loadingPodcasts = $state(true);
	let showAddPodcast = $state(false);
	let newPodcastName = $state('');
	let newPodcastUrl = $state('');
	let expandedPodcast = $state<number | null>(null);

	// Playlists
	let allPlaylists = $state<PlaylistSummary[]>([]);
	let loadingPlaylists = $state(true);
	let showNewPlaylist = $state(false);
	let newPlaylistName = $state('');
	let expandedPlaylist = $state<PlaylistDetail | null>(null);
	let showAddItem = $state(false);
	let newItemPath = $state('');
	let newItemTitle = $state('');

	onMount(() => { loadFolders(); loadRadio(); loadPodcasts(); loadPlaylists(); });

	async function loadFolders() { loadingFolders = true; try { folders = await library.folders(); } catch (e) { error = String(e); } finally { loadingFolders = false; } }
	async function loadRadio() { loadingRadio = true; try { stations = await streams.listRadio(); } catch (e) { error = String(e); } finally { loadingRadio = false; } }
	async function loadPodcasts() { loadingPodcasts = true; try { podcasts = await streams.listPodcasts(); } catch (e) { error = String(e); } finally { loadingPodcasts = false; } }
	async function loadPlaylists() { loadingPlaylists = true; try { allPlaylists = await playlistsApi.list(); } catch (e) { error = String(e); } finally { loadingPlaylists = false; } }

	async function playContent(type: 'folder' | 'url', path: string) {
		try {
			const endpoint = type === 'folder' ? '/api/player/play-folder' : '/api/player/play-url';
			const body = type === 'folder' ? { path } : { url: path };
			await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
			goto('/');
		} catch {}
	}

	// Folder actions
	async function createFolder() { if (!newFolderName.trim()) return; await library.createFolder(newFolderName.trim()); newFolderName = ''; showNewFolder = false; await loadFolders(); }
	async function deleteFolder(name: string) { await library.deleteFolder(name); if (expandedFolder === name) expandedFolder = null; await loadFolders(); }
	async function toggleFolder(name: string) { if (expandedFolder === name) { expandedFolder = null; folderTracks = []; } else { expandedFolder = name; folderTracks = await library.tracks(name); } }
	async function handleFiles(folderName: string, files: FileList) {
		uploadFolder = folderName; uploading = true;
		for (let i = 0; i < files.length; i++) { uploadProgress = 0; await library.upload(folderName, files[i], (pct) => { uploadProgress = pct; }); }
		uploading = false; uploadFolder = ''; await loadFolders();
		if (expandedFolder === folderName) folderTracks = await library.tracks(folderName);
	}

	// Radio actions
	function isValidUrl(url: string): boolean { try { const u = new URL(url); return u.protocol === 'http:' || u.protocol === 'https:'; } catch { return false; } }
	async function addStation() { urlError = ''; if (!newStationName.trim() || !newStationUrl.trim()) return; if (!isValidUrl(newStationUrl)) { urlError = t('content.radio_url_invalid'); return; } await streams.addRadio(newStationName.trim(), newStationUrl.trim()); newStationName = ''; newStationUrl = ''; showAddStation = false; await loadRadio(); }
	async function removeStation(id: number) { await streams.deleteRadio(id); expandedRadio = null; await loadRadio(); }

	// Podcast actions
	async function addPodcast() { urlError = ''; if (!newPodcastName.trim() || !newPodcastUrl.trim()) return; if (!isValidUrl(newPodcastUrl)) { urlError = t('content.radio_url_invalid'); return; } await streams.addPodcast(newPodcastName.trim(), newPodcastUrl.trim()); newPodcastName = ''; newPodcastUrl = ''; showAddPodcast = false; await loadPodcasts(); }
	async function removePodcast(id: number) { await streams.deletePodcast(id); expandedPodcast = null; await loadPodcasts(); }

	// Playlist actions
	async function createPlaylist() { if (!newPlaylistName.trim()) return; await playlistsApi.create(newPlaylistName.trim()); newPlaylistName = ''; showNewPlaylist = false; await loadPlaylists(); }
	async function removePlaylist(id: number) { await playlistsApi.delete(id); if (expandedPlaylist?.id === id) expandedPlaylist = null; await loadPlaylists(); }
	async function togglePlaylist(id: number) { if (expandedPlaylist?.id === id) { expandedPlaylist = null; } else { expandedPlaylist = await playlistsApi.get(id); } }
	async function addPlaylistItem() { if (!expandedPlaylist || !newItemPath.trim()) return; await playlistsApi.addItem(expandedPlaylist.id, 'folder', newItemPath.trim(), newItemTitle.trim() || undefined); newItemPath = ''; newItemTitle = ''; showAddItem = false; expandedPlaylist = await playlistsApi.get(expandedPlaylist.id); await loadPlaylists(); }
	async function removePlaylistItem(itemId: number) { if (!expandedPlaylist) return; await playlistsApi.removeItem(itemId); expandedPlaylist = await playlistsApi.get(expandedPlaylist.id); await loadPlaylists(); }

	function formatSize(bytes: number): string { if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`; return `${(bytes / (1024 * 1024)).toFixed(1)} MB`; }
</script>

<!--
  UNIFIED ROW: [ ▶ play ]  Title + Subtitle  [  ˅ chevron  ]
  Play = circle button, primary color, leftmost
  Center = clickable to expand
  Chevron = rightmost, rotates on expand
  Delete = only inside expanded area
-->

<div class="p-4">
	<h1 class="text-xl font-bold mb-4">{t('library.title')}</h1>

	<div class="flex gap-2 mb-4 overflow-x-auto">
		{#each [['folders', t('content.tab_folders')], ['radio', t('content.tab_radio')], ['podcasts', t('content.tab_podcasts')], ['playlists', t('content.tab_playlists')]] as [key, label]}
			<button onclick={() => (tab = key as Tab)}
				class="px-3 py-1.5 text-xs font-medium rounded-full whitespace-nowrap transition-colors {tab === key ? 'bg-primary text-white' : 'bg-surface-light text-text-muted hover:text-text'}"
			>{label}</button>
		{/each}
	</div>

	{#if error}<div class="text-sm text-red-400 mb-3">{error}</div>{/if}

	<!-- ===================== FOLDERS ===================== -->
	{#if tab === 'folders'}
		<div class="flex justify-end mb-3">
			{#if showNewFolder}
				<button onclick={() => (showNewFolder = false)} class="text-sm text-text-muted">{t('content.close_form')}</button>
			{:else}
				<button onclick={() => (showNewFolder = true)} class="text-sm text-primary font-medium">+ {t('content.new_folder')}</button>
			{/if}
		</div>
		{#if showNewFolder}
			<div class="flex gap-2 mb-4 p-3 bg-surface-light rounded-xl">
				<input type="text" bind:value={newFolderName} placeholder={t('content.folder_name')} class="flex-1 px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary" onkeydown={(e) => e.key === 'Enter' && createFolder()} />
				<button onclick={createFolder} class="px-4 py-2 bg-primary text-white rounded-lg text-sm">{t('general.save')}</button>
			</div>
		{/if}
		{#if loadingFolders}
			<div class="flex justify-center py-12"><div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div></div>
		{:else if folders.length === 0}
			<div class="text-center py-16 text-text-muted"><p class="text-sm">{t('library.empty')}</p><p class="text-xs mt-1">{t('library.empty_hint')}</p></div>
		{:else}
			<div class="flex flex-col gap-2">
				{#each folders as folder (folder.path)}
					{@const expanded = expandedFolder === folder.path}
					<div class="bg-surface-light rounded-xl overflow-hidden">
						<div class="flex items-center gap-3 p-3">
							<!-- Play circle -->
							<button onclick={() => playContent('folder', folder.path)} class="w-10 h-10 rounded-full bg-primary/10 hover:bg-primary/20 flex items-center justify-center flex-shrink-0 transition-colors" aria-label="Abspielen">
								<svg class="w-5 h-5 text-primary ml-0.5" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
							</button>
							<!-- Info (click to expand) -->
							<button onclick={() => toggleFolder(folder.path)} class="flex-1 min-w-0 text-left">
								<p class="text-sm font-medium text-text truncate">{folder.name}</p>
								<p class="text-xs text-text-muted">{t('content.tracks', { count: folder.track_count })} · {formatSize(folder.size_bytes)}</p>
							</button>
							<!-- Chevron -->
							<button onclick={() => toggleFolder(folder.path)} class="p-1">
								<svg class="w-4 h-4 text-text-muted transition-transform {expanded ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
							</button>
						</div>
						{#if expanded}
							<div class="px-3 pb-3 border-t border-surface-lighter">
								<div class="flex items-center gap-2 py-2">
									<label class="flex items-center gap-1.5 px-3 py-1.5 bg-surface-lighter rounded-lg text-xs text-text-muted hover:text-text cursor-pointer">
										<svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/></svg>
										Hochladen
										<input type="file" multiple accept="audio/*,image/*" class="hidden" onchange={(e) => { const t = e.target as HTMLInputElement; if (t.files) handleFiles(folder.path, t.files); }} />
									</label>
								</div>
								{#if uploading && uploadFolder === folder.path}
									<div class="mb-2 h-1.5 bg-surface-lighter rounded-full overflow-hidden"><div class="h-full bg-primary transition-[width] duration-200" style="width: {uploadProgress}%"></div></div>
								{/if}
								{#if folderTracks.length > 0}
									<div class="flex flex-col">
										{#each folderTracks as track, i}
											<div class="flex items-center gap-2 py-1.5 text-xs {i > 0 ? 'border-t border-surface-lighter/50' : ''}">
												<span class="w-5 text-text-muted text-right tabular-nums">{i + 1}</span>
												<span class="text-text truncate">{track.filename}</span>
											</div>
										{/each}
									</div>
								{:else}
									<p class="text-xs text-text-muted py-2">Keine Titel in diesem Ordner.</p>
								{/if}
								<div class="mt-2 pt-2 border-t border-surface-lighter">
									<button onclick={() => deleteFolder(folder.path)} class="text-xs text-red-400 hover:text-red-300">Ordner löschen</button>
								</div>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	{/if}

	<!-- ===================== RADIO ===================== -->
	{#if tab === 'radio'}
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
		{#if loadingRadio}
			<div class="flex justify-center py-12"><div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div></div>
		{:else}
			<div class="flex flex-col gap-2">
				{#each stations as station (station.id)}
					{@const expanded = expandedRadio === station.id}
					<div class="bg-surface-light rounded-xl overflow-hidden">
						<div class="flex items-center gap-3 p-3">
							<button onclick={() => playContent('url', station.url)} class="w-10 h-10 rounded-full bg-primary/10 hover:bg-primary/20 flex items-center justify-center flex-shrink-0 transition-colors" aria-label="Abspielen">
								<svg class="w-5 h-5 text-primary ml-0.5" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
							</button>
							<button onclick={() => (expandedRadio = expanded ? null : station.id)} class="flex-1 min-w-0 text-left">
								<p class="text-sm font-medium text-text truncate">{station.name}</p>
								<p class="text-xs text-text-muted">{station.category === 'kinder' ? 'Kindersender' : 'Eigener Sender'}</p>
							</button>
							<button onclick={() => (expandedRadio = expanded ? null : station.id)} class="p-1">
								<svg class="w-4 h-4 text-text-muted transition-transform {expanded ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
							</button>
						</div>
						{#if expanded}
							<div class="px-3 pb-3 border-t border-surface-lighter">
								<p class="text-[10px] text-text-muted font-mono py-2 truncate">{station.url}</p>
								<button onclick={() => removeStation(station.id)} class="text-xs text-red-400 hover:text-red-300">Sender löschen</button>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	{/if}

	<!-- ===================== PODCASTS ===================== -->
	{#if tab === 'podcasts'}
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
		{#if loadingPodcasts}
			<div class="flex justify-center py-12"><div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div></div>
		{:else if podcasts.length === 0}
			<div class="text-center py-12 text-text-muted text-sm">Noch keine Podcasts hinzugefügt.</div>
		{:else}
			<div class="flex flex-col gap-2">
				{#each podcasts as podcast (podcast.id)}
					{@const expanded = expandedPodcast === podcast.id}
					<div class="bg-surface-light rounded-xl overflow-hidden">
						<div class="flex items-center gap-3 p-3">
							<button onclick={() => playContent('url', podcast.feed_url)} class="w-10 h-10 rounded-full bg-primary/10 hover:bg-primary/20 flex items-center justify-center flex-shrink-0 transition-colors" aria-label="Abspielen">
								<svg class="w-5 h-5 text-primary ml-0.5" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
							</button>
							<button onclick={() => (expandedPodcast = expanded ? null : podcast.id)} class="flex-1 min-w-0 text-left">
								<p class="text-sm font-medium text-text truncate">{podcast.name}</p>
								<p class="text-xs text-text-muted">{podcast.episode_count} Folgen</p>
							</button>
							<button onclick={() => (expandedPodcast = expanded ? null : podcast.id)} class="p-1">
								<svg class="w-4 h-4 text-text-muted transition-transform {expanded ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
							</button>
						</div>
						{#if expanded}
							<div class="px-3 pb-3 border-t border-surface-lighter">
								<p class="text-[10px] text-text-muted font-mono py-2 truncate">{podcast.feed_url}</p>
								<button onclick={() => removePodcast(podcast.id)} class="text-xs text-red-400 hover:text-red-300">Podcast löschen</button>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	{/if}

	<!-- ===================== PLAYLISTS ===================== -->
	{#if tab === 'playlists'}
		<div class="flex justify-end mb-3">
			{#if showNewPlaylist}
				<button onclick={() => (showNewPlaylist = false)} class="text-sm text-text-muted">{t('content.close_form')}</button>
			{:else}
				<button onclick={() => (showNewPlaylist = true)} class="text-sm text-primary font-medium">+ {t('content.playlist_new')}</button>
			{/if}
		</div>
		{#if showNewPlaylist}
			<div class="flex gap-2 mb-4 p-3 bg-surface-light rounded-xl">
				<input type="text" bind:value={newPlaylistName} placeholder={t('content.playlist_name')} class="flex-1 px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary" onkeydown={(e) => e.key === 'Enter' && createPlaylist()} />
				<button onclick={createPlaylist} class="px-4 py-2 bg-primary text-white rounded-lg text-sm">{t('general.save')}</button>
			</div>
		{/if}
		{#if loadingPlaylists}
			<div class="flex justify-center py-12"><div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div></div>
		{:else if allPlaylists.length === 0}
			<div class="text-center py-12 text-text-muted text-sm">{t('content.playlist_empty')}</div>
		{:else}
			<div class="flex flex-col gap-2">
				{#each allPlaylists as pl (pl.id)}
					{@const expanded = expandedPlaylist?.id === pl.id}
					<div class="bg-surface-light rounded-xl overflow-hidden">
						<div class="flex items-center gap-3 p-3">
							<button onclick={() => {/* TODO: play playlist */}} class="w-10 h-10 rounded-full bg-primary/10 hover:bg-primary/20 flex items-center justify-center flex-shrink-0 transition-colors {pl.item_count === 0 ? 'opacity-30' : ''}" aria-label="Abspielen" disabled={pl.item_count === 0}>
								<svg class="w-5 h-5 text-primary ml-0.5" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
							</button>
							<button onclick={() => togglePlaylist(pl.id)} class="flex-1 min-w-0 text-left">
								<p class="text-sm font-medium text-text truncate">{pl.name}</p>
								<p class="text-xs text-text-muted">{pl.item_count} Einträge</p>
							</button>
							<button onclick={() => togglePlaylist(pl.id)} class="p-1">
								<svg class="w-4 h-4 text-text-muted transition-transform {expanded ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
							</button>
						</div>
						{#if expanded}
							<div class="px-3 pb-3 border-t border-surface-lighter">
								<div class="py-2">
									{#if showAddItem}
										<div class="flex flex-col gap-2 p-2 bg-surface rounded-lg">
											{#if folders.length > 0}
												<p class="text-[10px] text-text-muted uppercase tracking-wider">Ordner auswählen</p>
												<div class="flex flex-wrap gap-1">
													{#each folders as f}
														<button onclick={() => { newItemPath = f.path; newItemTitle = f.name; }}
															class="px-2 py-1 rounded text-xs transition-colors {newItemPath === f.path ? 'bg-primary text-white' : 'bg-surface-lighter text-text-muted hover:text-text'}"
														>{f.name}</button>
													{/each}
												</div>
											{/if}
											<input type="text" bind:value={newItemPath} placeholder="Oder Pfad/URL manuell" class="px-2 py-1.5 bg-surface-light border border-surface-lighter rounded text-text text-xs focus:outline-none focus:border-primary" />
											<input type="text" bind:value={newItemTitle} placeholder="Anzeigename (optional)" class="px-2 py-1.5 bg-surface-light border border-surface-lighter rounded text-text text-xs focus:outline-none focus:border-primary" />
											<div class="flex gap-2 justify-end">
												<button onclick={() => (showAddItem = false)} class="text-xs text-text-muted">{t('general.cancel')}</button>
												<button onclick={addPlaylistItem} disabled={!newItemPath.trim()} class="px-3 py-1 bg-primary disabled:opacity-30 text-white rounded text-xs">{t('general.save')}</button>
											</div>
										</div>
									{:else}
										<button onclick={() => (showAddItem = true)} class="text-xs text-primary font-medium">+ Eintrag hinzufügen</button>
									{/if}
								</div>
								{#if expandedPlaylist && expandedPlaylist.items.length > 0}
									<div class="flex flex-col">
										{#each expandedPlaylist.items as item, i}
											<div class="flex items-center gap-2 py-1.5 text-xs {i > 0 ? 'border-t border-surface-lighter/50' : ''}">
												<span class="w-5 text-text-muted text-right tabular-nums">{item.position}</span>
												<span class="flex-1 text-text truncate">{item.title || item.content_path}</span>
												<button onclick={() => removePlaylistItem(item.id)} class="p-0.5 text-text-muted/40 hover:text-red-400">
													<svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
												</button>
											</div>
										{/each}
									</div>
								{:else}
									<p class="text-xs text-text-muted py-1">Noch keine Einträge.</p>
								{/if}
								<div class="mt-2 pt-2 border-t border-surface-lighter">
									<button onclick={() => removePlaylist(pl.id)} class="text-xs text-red-400 hover:text-red-300">Playlist löschen</button>
								</div>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	{/if}
</div>

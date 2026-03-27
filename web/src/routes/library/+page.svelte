<script lang="ts">
	import { t } from '$lib/i18n';
	import { library, streams, playlistsApi, player, type MediaFolder, type RadioStation, type PodcastInfo, type PlaylistSummary, type PlaylistDetail } from '$lib/api';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	type Tab = 'folders' | 'radio' | 'podcasts' | 'playlists';
	let tab = $state<Tab>('folders');

	// Folders
	let folders = $state<MediaFolder[]>([]);
	let loadingFolders = $state(true);
	let showNewFolder = $state(false);
	let newFolderName = $state('');
	let expandedFolder = $state<string | null>(null);
	let folderTracks = $state<{ filename: string; path: string }[]>([]);

	// Upload
	let uploadFolder = $state('');
	let uploadProgress = $state(0);
	let uploading = $state(false);

	// Radio
	let stations = $state<RadioStation[]>([]);
	let loadingRadio = $state(true);
	let showAddStation = $state(false);
	let newStationName = $state('');
	let newStationUrl = $state('');
	let stationUrlError = $state('');

	// Podcasts
	let podcasts = $state<PodcastInfo[]>([]);
	let loadingPodcasts = $state(true);
	let showAddPodcast = $state(false);
	let newPodcastName = $state('');
	let newPodcastUrl = $state('');
	let podcastUrlError = $state('');

	// Playlists
	let allPlaylists = $state<PlaylistSummary[]>([]);
	let loadingPlaylists = $state(true);
	let showNewPlaylist = $state(false);
	let newPlaylistName = $state('');
	let expandedPlaylist = $state<PlaylistDetail | null>(null);
	let showAddItem = $state(false);
	let newItemType = $state<'folder' | 'stream' | 'track'>('folder');
	let newItemPath = $state('');
	let newItemTitle = $state('');

	let error = $state('');

	onMount(() => {
		loadFolders();
		loadRadio();
		loadPodcasts();
		loadPlaylists();
	});

	async function loadFolders() {
		loadingFolders = true;
		try { folders = await library.folders(); } catch (e) { error = String(e); }
		finally { loadingFolders = false; }
	}

	async function loadRadio() {
		loadingRadio = true;
		try { stations = await streams.listRadio(); } catch (e) { error = String(e); }
		finally { loadingRadio = false; }
	}

	async function loadPodcasts() {
		loadingPodcasts = true;
		try { podcasts = await streams.listPodcasts(); } catch (e) { error = String(e); }
		finally { loadingPodcasts = false; }
	}

	async function createFolder() {
		if (!newFolderName.trim()) return;
		await library.createFolder(newFolderName.trim());
		newFolderName = '';
		showNewFolder = false;
		await loadFolders();
	}

	async function toggleFolder(folderName: string) {
		if (expandedFolder === folderName) {
			expandedFolder = null;
			folderTracks = [];
		} else {
			expandedFolder = folderName;
			folderTracks = await library.tracks(folderName);
		}
	}

	async function playFolder(folderPath: string) {
		try {
			await fetch('/api/player/play-folder', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ path: folderPath }),
			});
			goto('/');
		} catch {}
	}

	async function playRadio(url: string) {
		try {
			await fetch('/api/player/play-url', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ url }),
			});
			goto('/');
		} catch {}
	}

	async function handleFiles(folderName: string, files: FileList) {
		uploadFolder = folderName;
		uploading = true;
		for (let i = 0; i < files.length; i++) {
			uploadProgress = 0;
			await library.upload(folderName, files[i], (pct) => { uploadProgress = pct; });
		}
		uploading = false;
		uploadFolder = '';
		await loadFolders();
	}

	function isValidUrl(url: string): boolean {
		try {
			const u = new URL(url);
			return u.protocol === 'http:' || u.protocol === 'https:';
		} catch {
			return false;
		}
	}

	async function addStation() {
		stationUrlError = '';
		if (!newStationName.trim() || !newStationUrl.trim()) return;
		if (!isValidUrl(newStationUrl)) {
			stationUrlError = t('content.radio_url_invalid');
			return;
		}
		await streams.addRadio(newStationName.trim(), newStationUrl.trim());
		newStationName = '';
		newStationUrl = '';
		showAddStation = false;
		await loadRadio();
	}

	async function removeStation(id: number) {
		await streams.deleteRadio(id);
		await loadRadio();
	}

	async function addPodcast() {
		podcastUrlError = '';
		if (!newPodcastName.trim() || !newPodcastUrl.trim()) return;
		if (!isValidUrl(newPodcastUrl)) {
			podcastUrlError = t('content.radio_url_invalid');
			return;
		}
		await streams.addPodcast(newPodcastName.trim(), newPodcastUrl.trim());
		newPodcastName = '';
		newPodcastUrl = '';
		showAddPodcast = false;
		await loadPodcasts();
	}

	async function removePodcast(id: number) {
		await streams.deletePodcast(id);
		await loadPodcasts();
	}

	async function loadPlaylists() {
		loadingPlaylists = true;
		try { allPlaylists = await playlistsApi.list(); } catch (e) { error = String(e); }
		finally { loadingPlaylists = false; }
	}

	async function createPlaylist() {
		if (!newPlaylistName.trim()) return;
		await playlistsApi.create(newPlaylistName.trim());
		newPlaylistName = '';
		showNewPlaylist = false;
		await loadPlaylists();
	}

	async function removePlaylist(id: number) {
		await playlistsApi.delete(id);
		expandedPlaylist = null;
		await loadPlaylists();
	}

	async function togglePlaylist(id: number) {
		if (expandedPlaylist?.id === id) {
			expandedPlaylist = null;
		} else {
			expandedPlaylist = await playlistsApi.get(id);
		}
	}

	async function addPlaylistItem() {
		if (!expandedPlaylist || !newItemPath.trim()) return;
		await playlistsApi.addItem(expandedPlaylist.id, newItemType, newItemPath.trim(), newItemTitle.trim() || undefined);
		newItemPath = '';
		newItemTitle = '';
		showAddItem = false;
		expandedPlaylist = await playlistsApi.get(expandedPlaylist.id);
		await loadPlaylists();
	}

	async function removePlaylistItem(itemId: number) {
		if (!expandedPlaylist) return;
		await playlistsApi.removeItem(itemId);
		expandedPlaylist = await playlistsApi.get(expandedPlaylist.id);
		await loadPlaylists();
	}

	function formatSize(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}
</script>

<div class="p-4">
	<h1 class="text-xl font-bold mb-4">{t('library.title')}</h1>

	<!-- Tabs -->
	<div class="flex gap-2 mb-4">
		{#each [['folders', t('content.tab_folders')], ['radio', t('content.tab_radio')], ['podcasts', t('content.tab_podcasts')], ['playlists', t('content.tab_playlists')]] as [key, label]}
			<button
				onclick={() => (tab = key as Tab)}
				class="px-3 py-1.5 text-xs font-medium rounded-full transition-colors
					{tab === key ? 'bg-primary text-white' : 'bg-surface-light text-text-muted hover:text-text'}"
			>
				{label}
			</button>
		{/each}
	</div>

	{#if error}
		<div class="text-sm text-red-400 mb-3">{error}</div>
	{/if}

	<!-- Folders tab -->
	{#if tab === 'folders'}
		<div class="flex justify-end mb-3">
			{#if showNewFolder}
				<button onclick={() => (showNewFolder = false)} class="text-sm text-text-muted">{t('content.close_form')}</button>
			{:else}
				<button onclick={() => (showNewFolder = true)} class="text-sm text-primary font-medium">
					+ {t('content.new_folder')}
				</button>
			{/if}
		</div>

		{#if showNewFolder}
			<div class="flex gap-2 mb-4 p-3 bg-surface-light rounded-xl">
				<input
					type="text"
					bind:value={newFolderName}
					placeholder={t('content.folder_name')}
					class="flex-1 px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary"
					onkeydown={(e) => e.key === 'Enter' && createFolder()}
				/>
				<button onclick={createFolder} class="px-4 py-2 bg-primary text-white rounded-lg text-sm">{t('general.save')}</button>
			</div>
		{/if}

		{#if loadingFolders}
			<div class="flex justify-center py-12">
				<div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
			</div>
		{:else if folders.length === 0}
			<div class="text-center py-16 text-text-muted">
				<p class="text-sm">{t('library.empty')}</p>
				<p class="text-xs mt-1">{t('library.empty_hint')}</p>
			</div>
		{:else}
			<div class="flex flex-col gap-2">
				{#each folders as folder (folder.path)}
					<div class="bg-surface-light rounded-xl overflow-hidden">
						<!-- Folder header -->
						<button
							onclick={() => toggleFolder(folder.path)}
							class="w-full flex items-center gap-3 p-3 text-left hover:bg-surface-lighter transition-colors"
						>
							<div class="w-12 h-12 rounded-lg bg-surface-lighter flex-shrink-0 overflow-hidden flex items-center justify-center">
								{#if folder.cover_path}
									<img src={folder.cover_path} alt={folder.name} class="w-full h-full object-cover" />
								{:else}
									<svg class="w-6 h-6 text-text-muted opacity-30" viewBox="0 0 24 24" fill="currentColor">
										<path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/>
									</svg>
								{/if}
							</div>
							<div class="flex-1 min-w-0">
								<p class="text-sm font-medium text-text truncate">{folder.name}</p>
								<p class="text-xs text-text-muted">
									{t('content.tracks', { count: folder.track_count })} · {formatSize(folder.size_bytes)}
								</p>
							</div>
							<svg class="w-4 h-4 text-text-muted shrink-0 transition-transform {expandedFolder === folder.path ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<path d="M6 9l6 6 6-6"/>
							</svg>
						</button>

						<!-- Expanded: tracks + actions -->
						{#if expandedFolder === folder.path}
							<div class="px-3 pb-3 border-t border-surface-lighter">
								<!-- Actions row -->
								<div class="flex items-center gap-2 py-2">
									<button
										onclick={() => playFolder(folder.path)}
										class="flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 text-primary rounded-lg text-xs font-medium hover:bg-primary/20"
									>
										<svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
											<path d="M8 5v14l11-7z"/>
										</svg>
										{t('library.play_folder')}
									</button>
									<!-- Upload -->
									<label class="flex items-center gap-1.5 px-3 py-1.5 bg-surface-lighter rounded-lg text-xs text-text-muted hover:text-text cursor-pointer">
										<svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
											<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
										</svg>
										Hochladen
										<input
											type="file"
											multiple
											accept="audio/*,image/*"
											class="hidden"
											onchange={(e) => {
												const target = e.target as HTMLInputElement;
												if (target.files) handleFiles(folder.path, target.files);
											}}
										/>
									</label>
								</div>

								{#if uploading && uploadFolder === folder.path}
									<div class="mb-2 h-1.5 bg-surface-lighter rounded-full overflow-hidden">
										<div class="h-full bg-primary transition-[width] duration-200" style="width: {uploadProgress}%"></div>
									</div>
								{/if}

								<!-- Track list -->
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
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	{/if}

	<!-- Radio tab -->
	{#if tab === 'radio'}
		<div class="flex justify-end mb-3">
			{#if showAddStation}
				<button onclick={() => { showAddStation = false; stationUrlError = ''; }} class="text-sm text-text-muted">{t('content.close_form')}</button>
			{:else}
				<button onclick={() => (showAddStation = true)} class="text-sm text-primary font-medium">
					+ {t('content.radio_add')}
				</button>
			{/if}
		</div>

		{#if showAddStation}
			<div class="flex flex-col gap-2 mb-4 p-3 bg-surface-light rounded-xl">
				<input type="text" bind:value={newStationName} placeholder={t('content.radio_name')}
					class="px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary" />
				<input type="url" bind:value={newStationUrl} placeholder={t('content.radio_url')}
					class="px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary {stationUrlError ? 'border-red-500' : ''}" />
				{#if stationUrlError}
					<p class="text-xs text-red-400">{stationUrlError}</p>
				{/if}
				<button onclick={addStation} class="px-4 py-2 bg-primary text-white rounded-lg text-sm self-end">{t('general.save')}</button>
			</div>
		{/if}

		{#if loadingRadio}
			<div class="flex justify-center py-12">
				<div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
			</div>
		{:else}
			<div class="flex flex-col gap-2">
				{#each stations as station (station.id)}
					<div class="flex items-center gap-3 p-3 bg-surface-light rounded-xl">
						<div class="w-10 h-10 rounded-lg bg-surface-lighter flex items-center justify-center flex-shrink-0">
							<svg class="w-5 h-5 text-primary" viewBox="0 0 24 24" fill="currentColor">
								<path d="M3.24 6.15C2.51 6.43 2 7.17 2 8v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8c0-.83-.47-1.57-1.24-1.85L12 2 3.24 6.15zM12 16a3 3 0 1 1 0-6 3 3 0 0 1 0 6z"/>
							</svg>
						</div>
						<div class="flex-1 min-w-0">
							<p class="text-sm font-medium text-text truncate">{station.name}</p>
							<p class="text-[10px] text-text-muted truncate font-mono">{station.url}</p>
						</div>
						<button onclick={() => playRadio(station.url)} class="p-1.5 text-text-muted hover:text-primary transition-colors">
							<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
								<path d="M8 5v14l11-7z"/>
							</svg>
						</button>
						<button onclick={() => removeStation(station.id)} class="p-1.5 text-text-muted hover:text-red-400">
							<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<path d="M18 6L6 18M6 6l12 12"/>
							</svg>
						</button>
					</div>
				{/each}
			</div>
		{/if}
	{/if}

	<!-- Podcasts tab -->
	{#if tab === 'podcasts'}
		<div class="flex justify-end mb-3">
			{#if showAddPodcast}
				<button onclick={() => { showAddPodcast = false; podcastUrlError = ''; }} class="text-sm text-text-muted">{t('content.close_form')}</button>
			{:else}
				<button onclick={() => (showAddPodcast = true)} class="text-sm text-primary font-medium">
					+ {t('content.podcast_add')}
				</button>
			{/if}
		</div>

		{#if showAddPodcast}
			<div class="flex flex-col gap-2 mb-4 p-3 bg-surface-light rounded-xl">
				<input type="text" bind:value={newPodcastName} placeholder={t('content.podcast_name')}
					class="px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary" />
				<input type="url" bind:value={newPodcastUrl} placeholder={t('content.podcast_url')}
					class="px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary {podcastUrlError ? 'border-red-500' : ''}" />
				{#if podcastUrlError}
					<p class="text-xs text-red-400">{podcastUrlError}</p>
				{/if}
				<button onclick={addPodcast} class="px-4 py-2 bg-primary text-white rounded-lg text-sm self-end">{t('general.save')}</button>
			</div>
		{/if}

		{#if loadingPodcasts}
			<div class="flex justify-center py-12">
				<div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
			</div>
		{:else if podcasts.length === 0}
			<div class="text-center py-12 text-text-muted text-sm">
				Noch keine Podcasts hinzugefügt.
			</div>
		{:else}
			<div class="flex flex-col gap-2">
				{#each podcasts as podcast (podcast.id)}
					<div class="flex items-center gap-3 p-3 bg-surface-light rounded-xl">
						<div class="w-10 h-10 rounded-lg bg-surface-lighter flex items-center justify-center flex-shrink-0">
							<svg class="w-5 h-5 text-accent" viewBox="0 0 24 24" fill="currentColor">
								<path d="M6 18.5c0 .83.67 1.5 1.5 1.5h9c.83 0 1.5-.67 1.5-1.5V15h-3v2H9v-2H6v3.5zM12 2C8.69 2 6 4.69 6 8s2.69 6 6 6 6-2.69 6-6-2.69-6-6-6zm0 10c-2.21 0-4-1.79-4-4s1.79-4 4-4 4 1.79 4 4-1.79 4-4 4z"/>
							</svg>
						</div>
						<div class="flex-1 min-w-0">
							<p class="text-sm font-medium text-text truncate">{podcast.name}</p>
							<p class="text-xs text-text-muted">{podcast.episode_count} Folgen</p>
						</div>
						<button onclick={() => removePodcast(podcast.id)} class="p-1.5 text-text-muted hover:text-red-400">
							<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<path d="M18 6L6 18M6 6l12 12"/>
							</svg>
						</button>
					</div>
				{/each}
			</div>
		{/if}
	{/if}

	<!-- Playlists tab -->
	{#if tab === 'playlists'}
		<div class="flex justify-end mb-3">
			{#if showNewPlaylist}
				<button onclick={() => (showNewPlaylist = false)} class="text-sm text-text-muted">{t('content.close_form')}</button>
			{:else}
				<button onclick={() => (showNewPlaylist = true)} class="text-sm text-primary font-medium">
					+ {t('content.playlist_new')}
				</button>
			{/if}
		</div>

		{#if showNewPlaylist}
			<div class="flex gap-2 mb-4 p-3 bg-surface-light rounded-xl">
				<input
					type="text"
					bind:value={newPlaylistName}
					placeholder={t('content.playlist_name')}
					class="flex-1 px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary"
					onkeydown={(e) => e.key === 'Enter' && createPlaylist()}
				/>
				<button onclick={createPlaylist} class="px-4 py-2 bg-primary text-white rounded-lg text-sm">{t('general.save')}</button>
			</div>
		{/if}

		{#if loadingPlaylists}
			<div class="flex justify-center py-12">
				<div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
			</div>
		{:else if allPlaylists.length === 0}
			<div class="text-center py-12 text-text-muted text-sm">
				{t('content.playlist_empty')}
			</div>
		{:else}
			<div class="flex flex-col gap-2">
				{#each allPlaylists as pl (pl.id)}
					<div class="bg-surface-light rounded-xl overflow-hidden">
						<!-- Playlist header -->
						<button
							onclick={() => togglePlaylist(pl.id)}
							class="w-full flex items-center gap-3 p-3 text-left hover:bg-surface-lighter transition-colors"
						>
							<div class="w-10 h-10 rounded-lg bg-surface-lighter flex items-center justify-center flex-shrink-0">
								<svg class="w-5 h-5 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<line x1="8" y1="6" x2="21" y2="6"/>
									<line x1="8" y1="12" x2="21" y2="12"/>
									<line x1="8" y1="18" x2="21" y2="18"/>
									<line x1="3" y1="6" x2="3.01" y2="6"/>
									<line x1="3" y1="12" x2="3.01" y2="12"/>
									<line x1="3" y1="18" x2="3.01" y2="18"/>
								</svg>
							</div>
							<div class="flex-1 min-w-0">
								<p class="text-sm font-medium text-text truncate">{pl.name}</p>
								<p class="text-xs text-text-muted">{pl.item_count} Einträge</p>
							</div>
							<svg class="w-4 h-4 text-text-muted shrink-0 transition-transform {expandedPlaylist?.id === pl.id ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<path d="M6 9l6 6 6-6"/>
							</svg>
						</button>

						<!-- Expanded: items + add -->
						{#if expandedPlaylist?.id === pl.id}
							<div class="px-3 pb-3 border-t border-surface-lighter">
								<!-- Add item button -->
								<div class="py-2">
									{#if showAddItem}
										<div class="flex flex-col gap-2 p-2 bg-surface rounded-lg">
											<div class="flex gap-2">
												{#each ['folder', 'stream', 'track'] as type}
													<button
														onclick={() => (newItemType = type as any)}
														class="px-2 py-1 rounded text-xs {newItemType === type ? 'bg-primary text-white' : 'bg-surface-lighter text-text-muted'}"
													>
														{type === 'folder' ? 'Ordner' : type === 'stream' ? 'Stream' : 'Titel'}
													</button>
												{/each}
											</div>
											<input type="text" bind:value={newItemPath} placeholder="Pfad oder URL"
												class="px-2 py-1.5 bg-surface-light border border-surface-lighter rounded text-text text-xs focus:outline-none focus:border-primary" />
											<input type="text" bind:value={newItemTitle} placeholder="Anzeigename (optional)"
												class="px-2 py-1.5 bg-surface-light border border-surface-lighter rounded text-text text-xs focus:outline-none focus:border-primary" />
											<div class="flex gap-2 justify-end">
												<button onclick={() => (showAddItem = false)} class="text-xs text-text-muted">{t('general.cancel')}</button>
												<button onclick={addPlaylistItem} class="px-3 py-1 bg-primary text-white rounded text-xs">{t('general.save')}</button>
											</div>
										</div>
									{:else}
										<button onclick={() => (showAddItem = true)} class="text-xs text-primary font-medium">+ Eintrag hinzufügen</button>
									{/if}
								</div>

								<!-- Item list -->
								{#if expandedPlaylist.items.length > 0}
									<div class="flex flex-col">
										{#each expandedPlaylist.items as item, i}
											<div class="flex items-center gap-2 py-1.5 text-xs {i > 0 ? 'border-t border-surface-lighter/50' : ''}">
												<span class="w-5 text-text-muted text-right tabular-nums">{item.position}</span>
												<span class="flex-1 text-text truncate">{item.title || item.content_path}</span>
												<span class="text-text-muted capitalize text-[10px]">{item.content_type}</span>
												<button onclick={() => removePlaylistItem(item.id)} class="p-0.5 text-text-muted hover:text-red-400">
													<svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
														<path d="M18 6L6 18M6 6l12 12"/>
													</svg>
												</button>
											</div>
										{/each}
									</div>
								{:else}
									<p class="text-xs text-text-muted py-1">Noch keine Einträge.</p>
								{/if}

								<!-- Delete playlist -->
								<div class="mt-2 pt-2 border-t border-surface-lighter">
									<button onclick={() => removePlaylist(pl.id)} class="text-xs text-red-400 hover:text-red-300">
										Playlist löschen
									</button>
								</div>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	{/if}
</div>

<script lang="ts">
	import { t } from '$lib/i18n';
	import { library, streams, type MediaFolder, type RadioStation, type PodcastInfo } from '$lib/api';
	import { onMount } from 'svelte';

	type Tab = 'folders' | 'radio' | 'podcasts';
	let tab = $state<Tab>('folders');

	// Folders
	let folders = $state<MediaFolder[]>([]);
	let loadingFolders = $state(true);
	let showNewFolder = $state(false);
	let newFolderName = $state('');

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

	// Podcasts
	let podcasts = $state<PodcastInfo[]>([]);
	let loadingPodcasts = $state(true);
	let showAddPodcast = $state(false);
	let newPodcastName = $state('');
	let newPodcastUrl = $state('');

	let error = $state('');

	onMount(() => {
		loadFolders();
		loadRadio();
		loadPodcasts();
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

	async function addStation() {
		if (!newStationName.trim() || !newStationUrl.trim()) return;
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
		if (!newPodcastName.trim() || !newPodcastUrl.trim()) return;
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
		{#each [['folders', t('content.tab_folders')], ['radio', t('content.tab_radio')], ['podcasts', t('content.tab_podcasts')]] as [key, label]}
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
			<button onclick={() => (showNewFolder = !showNewFolder)} class="text-sm text-primary font-medium">
				+ {t('content.new_folder')}
			</button>
		</div>

		{#if showNewFolder}
			<div class="flex gap-2 mb-4">
				<input
					type="text"
					bind:value={newFolderName}
					placeholder={t('content.folder_name')}
					class="flex-1 px-3 py-2 bg-surface-light border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary"
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
					<div class="bg-surface-light rounded-xl p-3">
						<div class="flex items-center gap-3">
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
							<!-- Upload button for this folder -->
							<label class="p-2 text-text-muted hover:text-primary cursor-pointer transition-colors">
								<svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
								</svg>
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
							<div class="mt-2 h-1.5 bg-surface-lighter rounded-full overflow-hidden">
								<div class="h-full bg-primary transition-[width] duration-200" style="width: {uploadProgress}%"></div>
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
			<button onclick={() => (showAddStation = !showAddStation)} class="text-sm text-primary font-medium">
				+ {t('content.radio_add')}
			</button>
		</div>

		{#if showAddStation}
			<div class="flex flex-col gap-2 mb-4 p-3 bg-surface-light rounded-xl">
				<input type="text" bind:value={newStationName} placeholder={t('content.radio_name')}
					class="px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary" />
				<input type="url" bind:value={newStationUrl} placeholder={t('content.radio_url')}
					class="px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary" />
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
			<button onclick={() => (showAddPodcast = !showAddPodcast)} class="text-sm text-primary font-medium">
				+ {t('content.podcast_add')}
			</button>
		</div>

		{#if showAddPodcast}
			<div class="flex flex-col gap-2 mb-4 p-3 bg-surface-light rounded-xl">
				<input type="text" bind:value={newPodcastName} placeholder={t('content.podcast_name')}
					class="px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary" />
				<input type="url" bind:value={newPodcastUrl} placeholder={t('content.podcast_url')}
					class="px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary" />
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
</div>

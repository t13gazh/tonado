<script lang="ts">
	import { t } from '$lib/i18n';
	import {
		cards, library, streams, playlistsApi, config,
		type MediaFolder, type MediaTrack, type RadioStation,
		type PodcastInfo, type PlaylistSummary,
	} from '$lib/api';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	type Step = 'scan' | 'content' | 'done';
	type ContentType = 'folder' | 'stream' | 'podcast' | 'playlist' | 'command';

	let step = $state<Step>('scan');
	let scanning = $state(false);
	let scannedCardId = $state('');
	let hasExisting = $state(false);
	let error = $state('');
	let expertMode = $state(false);

	// Content form
	let name = $state('');
	let contentType = $state<ContentType>('folder');
	let contentPath = $state('');

	// Content lists
	let folders = $state<MediaFolder[]>([]);
	let radioStations = $state<RadioStation[]>([]);
	let podcastList = $state<PodcastInfo[]>([]);
	let playlists = $state<PlaylistSummary[]>([]);

	// Expanded items for track/episode selection
	let expandedFolder = $state<string | null>(null);
	let folderTracks = $state<Record<string, MediaTrack[]>>({});
	let expandedPodcast = $state<number | null>(null);
	let podcastEpisodes = $state<Record<number, { title: string; audio_url: string }[]>>({});

	// Track/episode selection mode
	let selectingTrack = $state(false);
	let selectingEpisode = $state(false);

	// Commands available to all users
	const commands = [
		{ path: 'sleep_timer', label: () => t('wizard.command_sleep') },
		{ path: 'volume:30', label: () => t('wizard.command_volume_low') },
		{ path: 'volume:50', label: () => t('wizard.command_volume_mid') },
		{ path: 'volume:70', label: () => t('wizard.command_volume_high') },
		{ path: 'shuffle', label: () => t('wizard.command_shuffle') },
		{ path: 'next', label: () => t('wizard.command_next') },
		{ path: 'previous', label: () => t('wizard.command_prev') },
	];

	onMount(async () => {
		try {
			const cfg = await config.getAll();
			expertMode = cfg['wizard.expert_mode'] === true;
		} catch {}
		startScan();
	});

	async function loadContentLists() {
		try {
			const [f, r, p, pl] = await Promise.all([
				library.folders(),
				streams.listRadio(),
				streams.listPodcasts(),
				playlistsApi.list(),
			]);
			folders = f;
			radioStations = r;
			podcastList = p;
			playlists = pl;
		} catch {}
	}

	async function startScan() {
		scanning = true;
		error = '';
		try {
			const result = await cards.waitForScan(30);
			if (result.scanned && result.card_id) {
				scannedCardId = result.card_id;
				hasExisting = result.has_mapping ?? false;
				if (result.mapping) {
					name = result.mapping.name;
					contentType = result.mapping.content_type as ContentType;
					contentPath = result.mapping.content_path;
				}
				step = 'content';
				loadContentLists();
			} else {
				scanning = false;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Fehler';
			scanning = false;
		}
	}

	async function loadTracks(folderPath: string) {
		if (folderTracks[folderPath]) {
			expandedFolder = expandedFolder === folderPath ? null : folderPath;
			return;
		}
		try {
			const tracks = await library.tracks(folderPath);
			folderTracks[folderPath] = tracks;
			expandedFolder = folderPath;
		} catch {}
	}

	async function loadEpisodes(podcastId: number) {
		if (podcastEpisodes[podcastId]) {
			expandedPodcast = expandedPodcast === podcastId ? null : podcastId;
			return;
		}
		try {
			const eps = await streams.episodes(podcastId);
			podcastEpisodes[podcastId] = eps;
			expandedPodcast = podcastId;
		} catch {}
	}

	function selectFolder(path: string, folderName: string) {
		contentPath = path;
		if (!name) name = folderName;
		selectingTrack = false;
	}

	function selectTrack(track: MediaTrack, folderName: string) {
		contentPath = track.path;
		if (!name) name = folderName + ' — ' + track.filename.replace(/\.[^.]+$/, '');
		selectingTrack = false;
	}

	function selectRadio(station: RadioStation) {
		contentPath = station.url;
		if (!name) name = station.name;
	}

	function selectPodcast(podcast: PodcastInfo) {
		contentPath = podcast.feed_url;
		if (!name) name = podcast.name;
		selectingEpisode = false;
	}

	function selectEpisode(ep: { title: string; audio_url: string }, podcastName: string) {
		contentPath = ep.audio_url;
		if (!name) name = podcastName + ' — ' + ep.title;
		selectingEpisode = false;
	}

	function selectPlaylist(pl: PlaylistSummary) {
		contentPath = `playlist:${pl.id}`;
		if (!name) name = pl.name;
	}

	function selectCommand(path: string, label: string) {
		contentPath = path;
		if (!name) name = label;
	}

	function formatDuration(s: number): string {
		const m = Math.floor(s / 60);
		const sec = Math.floor(s % 60);
		return `${m}:${sec.toString().padStart(2, '0')}`;
	}

	async function saveCard() {
		if (!name.trim() || !contentPath.trim()) return;
		error = '';
		// Map playlist contentType to stream for backend (plays URLs)
		const backendType = contentType === 'playlist' ? 'playlist' : contentType;
		try {
			if (hasExisting) {
				await cards.update(scannedCardId, {
					name: name.trim(),
					content_type: backendType,
					content_path: contentPath.trim(),
				});
			} else {
				await cards.create({
					card_id: scannedCardId,
					name: name.trim(),
					content_type: backendType,
					content_path: contentPath.trim(),
				});
			}
			step = 'done';
		} catch (e) {
			error = e instanceof Error ? e.message : 'Fehler';
		}
	}

	const contentTypes: { value: ContentType; label: () => string; icon: string }[] = [
		{ value: 'folder', label: () => t('wizard.type_folder'), icon: 'M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z' },
		{ value: 'stream', label: () => t('wizard.type_radio'), icon: 'M3.24 6.15C2.51 6.43 2 7.17 2 8v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8c0-.83-.47-1.57-1.24-1.85L12 2 3.24 6.15zM12 16a3 3 0 1 1 0-6 3 3 0 0 1 0 6z' },
		{ value: 'podcast', label: () => t('wizard.type_podcast'), icon: 'M12 1a9 9 0 0 0-9 9v7a3 3 0 0 0 3 3h2v-8H5v-2a7 7 0 0 1 14 0v2h-3v8h2a3 3 0 0 0 3-3v-7a9 9 0 0 0-9-9z' },
		{ value: 'playlist', label: () => t('wizard.type_playlist'), icon: 'M15 6H3v2h12V6zm0 4H3v2h12v-2zM3 16h8v-2H3v2zM17 6v8.18c-.31-.11-.65-.18-1-.18-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3V8h3V6h-5z' },
		{ value: 'command', label: () => t('wizard.type_command'), icon: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z' },
	];
</script>

<div class="flex flex-col h-full p-4">
	<!-- Header -->
	<div class="flex items-center gap-3 mb-6">
		<a href="/cards" class="p-2 text-text-muted hover:text-text" aria-label={t('general.back')}>
			<svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<path d="M19 12H5M12 19l-7-7 7-7"/>
			</svg>
		</a>
		<h1 class="text-lg font-bold">{t('wizard.title')}</h1>
	</div>

	<!-- Step indicators -->
	<div class="flex items-center gap-2 mb-8 px-4">
		{#each ['scan', 'content', 'done'] as s, i}
			{@const completed = ['scan', 'content', 'done'].indexOf(step) > i}
			{@const active = s === step}
			<div class="flex-1 h-1 rounded-full {active || completed ? 'bg-primary' : 'bg-surface-lighter'}"></div>
		{/each}
	</div>

	<!-- Step: Scan -->
	{#if step === 'scan'}
		<div class="flex-1 flex flex-col items-center justify-center text-center gap-6">
			<div class="w-32 h-32 rounded-2xl bg-surface-light flex items-center justify-center animate-pulse">
				<svg class="w-16 h-16 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
					<rect x="2" y="4" width="14" height="16" rx="2"/>
					<path d="M18 8h2a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2"/>
					<circle cx="9" cy="12" r="3" fill="currentColor" stroke="none" class="animate-ping"/>
				</svg>
			</div>

			<div>
				<h2 class="text-lg font-semibold mb-1">{t('wizard.step_scan')}</h2>
				<p class="text-sm text-text-muted">{t('wizard.step_scan_desc')}</p>
			</div>

			{#if error}
				<p class="text-sm text-red-400">{error}</p>
			{/if}

			{#if !scanning}
				<button
					onclick={startScan}
					class="px-6 py-2.5 bg-primary hover:bg-primary-light text-white rounded-xl text-sm font-medium transition-colors"
				>
					{t('general.retry')}
				</button>
			{:else}
				<p class="text-sm text-text-muted animate-pulse">{t('wizard.scanning')}</p>
			{/if}
		</div>
	{/if}

	<!-- Step: Content selection -->
	{#if step === 'content'}
		<div class="flex-1 flex flex-col gap-4 overflow-hidden">
			{#if hasExisting}
				<div class="px-3 py-2 bg-accent/10 border border-accent/20 rounded-lg text-sm text-accent">
					{t('wizard.already_assigned')}
				</div>
			{/if}

			<!-- Content type selector -->
			<div>
				<span class="text-xs text-text-muted mb-2 block">{t('wizard.content_type')}</span>
				<div class="flex gap-1.5 overflow-x-auto pb-1">
					{#each contentTypes as ct}
						<button
							onclick={() => { contentType = ct.value; contentPath = ''; selectingTrack = false; selectingEpisode = false; }}
							class="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap
								{contentType === ct.value
									? 'bg-primary text-white'
									: 'bg-surface-light text-text-muted hover:text-text'}"
						>
							<svg class="w-4 h-4 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor"><path d={ct.icon}/></svg>
							{ct.label()}
						</button>
					{/each}
				</div>
			</div>

			<!-- Name -->
			<label class="block">
				<span class="text-xs text-text-muted mb-1 block">{t('wizard.content_name')}</span>
				<input
					type="text"
					bind:value={name}
					placeholder="Die drei ???, Folge 1"
					class="w-full px-3 py-2.5 bg-surface-light border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary placeholder:text-text-muted/50"
				/>
			</label>

			<!-- Content selection (scrollable) -->
			<div class="flex-1 overflow-y-auto min-h-0">
				<span class="text-xs text-text-muted mb-2 block">{t('wizard.select_content')}</span>

				<!-- FOLDER selection -->
				{#if contentType === 'folder'}
					<div class="flex flex-col gap-1">
						{#each folders as f}
							<div>
								<div class="flex items-center gap-2">
									<button
										onclick={() => selectFolder(f.path, f.name)}
										class="flex-1 flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors
											{contentPath === f.path && !selectingTrack ? 'bg-primary text-white' : 'bg-surface-light text-text hover:bg-surface-lighter'}"
									>
										<svg class="w-4 h-4 flex-shrink-0 opacity-50" viewBox="0 0 24 24" fill="currentColor"><path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>
										<span class="truncate">{f.name}</span>
										<span class="text-xs opacity-60 ml-auto flex-shrink-0">{f.track_count} Titel</span>
									</button>
									{#if f.track_count > 0}
										<button
											onclick={() => loadTracks(f.path)}
											class="p-2 text-text-muted hover:text-text rounded-lg"
											aria-label={t('wizard.expand_tracks')}
										>
											<svg class="w-4 h-4 transition-transform {expandedFolder === f.path ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
										</button>
									{/if}
								</div>
								<!-- Tracks inside folder -->
								{#if expandedFolder === f.path && folderTracks[f.path]}
									<div class="ml-6 mt-1 flex flex-col gap-0.5">
										{#each folderTracks[f.path] as track}
											<button
												onclick={() => selectTrack(track, f.name)}
												class="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm text-left transition-colors
													{contentPath === track.path ? 'bg-primary text-white' : 'bg-surface text-text-muted hover:text-text hover:bg-surface-light'}"
											>
												<svg class="w-3.5 h-3.5 flex-shrink-0 opacity-40" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55C7.79 13 6 14.79 6 17s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>
												<span class="truncate">{track.filename.replace(/\.[^.]+$/, '')}</span>
												<span class="text-xs opacity-50 ml-auto flex-shrink-0">{formatDuration(track.duration_seconds)}</span>
											</button>
										{/each}
									</div>
								{/if}
							</div>
						{/each}
						{#if folders.length === 0}
							<p class="text-sm text-text-muted py-4 text-center">{t('library.empty')}</p>
						{/if}
					</div>
				{/if}

				<!-- RADIO selection -->
				{#if contentType === 'stream'}
					<div class="flex flex-col gap-1">
						{#each radioStations as s}
							<button
								onclick={() => selectRadio(s)}
								class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors
									{contentPath === s.url ? 'bg-primary text-white' : 'bg-surface-light text-text hover:bg-surface-lighter'}"
							>
								<svg class="w-4 h-4 flex-shrink-0 opacity-50" viewBox="0 0 24 24" fill="currentColor"><path d="M3.24 6.15C2.51 6.43 2 7.17 2 8v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8c0-.83-.47-1.57-1.24-1.85L12 2 3.24 6.15zM12 16a3 3 0 1 1 0-6 3 3 0 0 1 0 6z"/></svg>
								<span class="truncate">{s.name}</span>
								{#if s.category}<span class="text-xs opacity-50 ml-auto">{s.category}</span>{/if}
							</button>
						{/each}
						{#if radioStations.length === 0}
							<p class="text-sm text-text-muted py-4 text-center">Keine Radiosender vorhanden</p>
						{/if}
					</div>
				{/if}

				<!-- PODCAST selection -->
				{#if contentType === 'podcast'}
					<div class="flex flex-col gap-1">
						{#each podcastList as p}
							<div>
								<div class="flex items-center gap-2">
									<button
										onclick={() => selectPodcast(p)}
										class="flex-1 flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors
											{contentPath === p.feed_url && !selectingEpisode ? 'bg-primary text-white' : 'bg-surface-light text-text hover:bg-surface-lighter'}"
									>
										<svg class="w-4 h-4 flex-shrink-0 opacity-50" viewBox="0 0 24 24" fill="currentColor"><path d="M12 1a9 9 0 0 0-9 9v7a3 3 0 0 0 3 3h2v-8H5v-2a7 7 0 0 1 14 0v2h-3v8h2a3 3 0 0 0 3-3v-7a9 9 0 0 0-9-9z"/></svg>
										<span class="truncate">{p.name}</span>
										<span class="text-xs opacity-60 ml-auto flex-shrink-0">{p.episode_count} Folgen</span>
									</button>
									{#if p.episode_count > 0}
										<button
											onclick={() => loadEpisodes(p.id)}
											class="p-2 text-text-muted hover:text-text rounded-lg"
											aria-label={t('wizard.expand_tracks')}
										>
											<svg class="w-4 h-4 transition-transform {expandedPodcast === p.id ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
										</button>
									{/if}
								</div>
								<!-- Episodes -->
								{#if expandedPodcast === p.id && podcastEpisodes[p.id]}
									<div class="ml-6 mt-1 flex flex-col gap-0.5 max-h-48 overflow-y-auto">
										{#each podcastEpisodes[p.id] as ep}
											<button
												onclick={() => selectEpisode(ep, p.name)}
												class="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm text-left transition-colors
													{contentPath === ep.audio_url ? 'bg-primary text-white' : 'bg-surface text-text-muted hover:text-text hover:bg-surface-light'}"
											>
												<svg class="w-3.5 h-3.5 flex-shrink-0 opacity-40" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
												<span class="truncate">{ep.title}</span>
											</button>
										{/each}
									</div>
								{/if}
							</div>
						{/each}
						{#if podcastList.length === 0}
							<p class="text-sm text-text-muted py-4 text-center">Keine Podcasts vorhanden</p>
						{/if}
					</div>
				{/if}

				<!-- PLAYLIST selection -->
				{#if contentType === 'playlist'}
					<div class="flex flex-col gap-1">
						{#each playlists as pl}
							<button
								onclick={() => selectPlaylist(pl)}
								class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors
									{contentPath === `playlist:${pl.id}` ? 'bg-primary text-white' : 'bg-surface-light text-text hover:bg-surface-lighter'}"
							>
								<svg class="w-4 h-4 flex-shrink-0 opacity-50" viewBox="0 0 24 24" fill="currentColor"><path d="M15 6H3v2h12V6zm0 4H3v2h12v-2zM3 16h8v-2H3v2zM17 6v8.18c-.31-.11-.65-.18-1-.18-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3V8h3V6h-5z"/></svg>
								<span class="truncate">{pl.name}</span>
								<span class="text-xs opacity-60 ml-auto flex-shrink-0">{pl.item_count} Titel</span>
							</button>
						{/each}
						{#if playlists.length === 0}
							<p class="text-sm text-text-muted py-4 text-center">{t('content.playlist_empty')}</p>
						{/if}
					</div>
				{/if}

				<!-- COMMAND selection -->
				{#if contentType === 'command'}
					<div class="flex flex-col gap-1">
						{#each commands as cmd}
							<button
								onclick={() => selectCommand(cmd.path, cmd.label())}
								class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors
									{contentPath === cmd.path ? 'bg-primary text-white' : 'bg-surface-light text-text hover:bg-surface-lighter'}"
							>
								<svg class="w-4 h-4 flex-shrink-0 opacity-50" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
								<span>{cmd.label()}</span>
							</button>
						{/each}
					</div>
				{/if}
			</div>

			<!-- Expert: manual path input -->
			{#if expertMode}
				<div class="pt-2 border-t border-surface-lighter">
					<p class="text-[10px] text-text-muted mb-1">{t('wizard.content_path')}</p>
					<input
						type="text"
						bind:value={contentPath}
						placeholder={contentType === 'stream' ? 'https://...' : 'Ordner/Datei.mp3'}
						class="w-full px-3 py-2 bg-surface-light border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary placeholder:text-text-muted/50 font-mono text-xs"
					/>
				</div>
			{/if}

			{#if error}
				<p class="text-sm text-red-400">{error}</p>
			{/if}

			<div class="flex gap-3 pt-2">
				<button
					onclick={() => { step = 'scan'; startScan(); }}
					class="flex-1 px-4 py-2.5 bg-surface border border-surface-lighter rounded-lg text-text-muted text-sm font-medium"
				>
					{t('general.back')}
				</button>
				<button
					onclick={saveCard}
					disabled={!name.trim() || !contentPath.trim()}
					class="flex-1 px-4 py-2.5 bg-primary hover:bg-primary-light disabled:opacity-50 rounded-lg text-white text-sm font-medium transition-colors"
				>
					{hasExisting ? t('wizard.reassign') : t('wizard.next')}
				</button>
			</div>
		</div>
	{/if}

	<!-- Step: Done -->
	{#if step === 'done'}
		<div class="flex-1 flex flex-col items-center justify-center text-center gap-6">
			<div class="w-20 h-20 rounded-full bg-green-500/20 flex items-center justify-center">
				<svg class="w-10 h-10 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
					<path d="M20 6L9 17l-5-5"/>
				</svg>
			</div>

			<div>
				<h2 class="text-lg font-semibold mb-1">{t('wizard.step_done')}</h2>
				<p class="text-sm text-text-muted max-w-xs">{t('wizard.done_desc')}</p>
			</div>

			<div class="flex flex-col gap-2 w-full max-w-xs">
				<button
					onclick={() => goto('/cards')}
					class="px-8 py-3 bg-primary hover:bg-primary-light text-white rounded-xl text-sm font-medium transition-colors"
				>
					{t('wizard.finish')}
				</button>
				<button
					onclick={() => { step = 'scan'; scannedCardId = ''; name = ''; contentPath = ''; hasExisting = false; startScan(); }}
					class="px-8 py-2.5 text-text-muted text-sm"
				>
					{t('card.add')}
				</button>
			</div>
		</div>
	{/if}
</div>

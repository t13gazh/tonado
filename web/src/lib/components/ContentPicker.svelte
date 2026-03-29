<script lang="ts">
	import { t } from '$lib/i18n';
	import {
		library, streams, playlistsApi,
		type MediaFolder, type MediaTrack, type RadioStation,
		type PodcastInfo, type PlaylistSummary,
	} from '$lib/api';
	import { onMount } from 'svelte';

	type ContentType = 'folder' | 'stream' | 'podcast' | 'playlist' | 'command';

	interface Props {
		contentType: ContentType;
		contentPath: string;
		name: string;
		expertMode?: boolean;
		onTypeChange: (type: ContentType) => void;
		onSelect: (path: string, name: string) => void;
	}

	let { contentType, contentPath, name, expertMode = false, onTypeChange, onSelect }: Props = $props();

	let folders = $state<MediaFolder[]>([]);
	let radioStations = $state<RadioStation[]>([]);
	let podcastList = $state<PodcastInfo[]>([]);
	let playlists = $state<PlaylistSummary[]>([]);
	let loaded = $state(false);

	// Expanded items for track/episode drill-down
	let expandedFolder = $state<string | null>(null);
	let folderTracks = $state<Record<string, MediaTrack[]>>({});
	let expandedPodcast = $state<number | null>(null);
	let podcastEpisodes = $state<Record<number, { title: string; audio_url: string }[]>>({});

	const commands = [
		{ path: 'sleep_timer', label: () => t('wizard.command_sleep'), icon: 'M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zm0 18c-4.4 0-8-3.6-8-8s3.6-8 8-8 8 3.6 8 8-3.6 8-8 8zm.5-13H11v6l5.2 3.2.8-1.3-4.5-2.7V7z' },
		{ path: 'volume:30', label: () => t('wizard.command_volume_low'), icon: 'M18.5 12c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM5 9v6h4l5 5V4L9 9H5z' },
		{ path: 'volume:50', label: () => t('wizard.command_volume_mid'), icon: 'M18.5 12c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM5 9v6h4l5 5V4L9 9H5z' },
		{ path: 'volume:70', label: () => t('wizard.command_volume_high'), icon: 'M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z' },
		{ path: 'shuffle', label: () => t('wizard.command_shuffle'), icon: 'M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z' },
		{ path: 'next', label: () => t('wizard.command_next'), icon: 'M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z' },
		{ path: 'previous', label: () => t('wizard.command_prev'), icon: 'M6 6h2v12H6zm3.5 6l8.5 6V6z' },
	];

	const contentTypes: { value: ContentType; label: () => string; icon: string }[] = [
		{ value: 'folder', label: () => t('wizard.type_folder'), icon: 'M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z' },
		{ value: 'stream', label: () => t('wizard.type_radio'), icon: 'M3.24 6.15C2.51 6.43 2 7.17 2 8v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8c0-.83-.47-1.57-1.24-1.85L12 2 3.24 6.15zM12 16a3 3 0 1 1 0-6 3 3 0 0 1 0 6z' },
		{ value: 'podcast', label: () => t('wizard.type_podcast'), icon: 'M12 1a9 9 0 0 0-9 9v7a3 3 0 0 0 3 3h2v-8H5v-2a7 7 0 0 1 14 0v2h-3v8h2a3 3 0 0 0 3-3v-7a9 9 0 0 0-9-9z' },
		{ value: 'playlist', label: () => t('wizard.type_playlist'), icon: 'M15 6H3v2h12V6zm0 4H3v2h12v-2zM3 16h8v-2H3v2zM17 6v8.18c-.31-.11-.65-.18-1-.18-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3V8h3V6h-5z' },
		{ value: 'command', label: () => t('wizard.type_command'), icon: 'M13 3h-2v10h2V3zm4.83 2.17l-1.42 1.42C17.99 7.86 19 9.81 19 12c0 3.87-3.13 7-7 7s-7-3.13-7-7c0-2.19 1.01-4.14 2.58-5.42L6.17 5.17C4.23 6.82 3 9.26 3 12c0 4.97 4.03 9 9 9s9-4.03 9-9c0-2.74-1.23-5.18-3.17-6.83z' },
	];

	function capitalize(s: string): string {
		return s.charAt(0).toUpperCase() + s.slice(1);
	}

	function formatDuration(s: number): string {
		const m = Math.floor(s / 60);
		const sec = Math.floor(s % 60);
		return `${m}:${sec.toString().padStart(2, '0')}`;
	}

	onMount(async () => {
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
		loaded = true;
	});

	async function loadTracks(folderPath: string) {
		if (folderTracks[folderPath]) {
			expandedFolder = expandedFolder === folderPath ? null : folderPath;
			return;
		}
		try {
			folderTracks[folderPath] = await library.tracks(folderPath);
			expandedFolder = folderPath;
		} catch {}
	}

	async function loadEpisodes(podcastId: number) {
		if (podcastEpisodes[podcastId]) {
			expandedPodcast = expandedPodcast === podcastId ? null : podcastId;
			return;
		}
		try {
			podcastEpisodes[podcastId] = await streams.episodes(podcastId);
			expandedPodcast = podcastId;
		} catch {}
	}

	function select(path: string, autoName: string) {
		onSelect(path, autoName);
	}
</script>

<!-- Content type tabs -->
<div>
	<span class="text-xs text-text-muted mb-2 block">{t('wizard.content_type')}</span>
	<div class="flex flex-wrap gap-1.5">
		{#each contentTypes as ct}
			<button
				onclick={() => onTypeChange(ct.value)}
				class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors
					{contentType === ct.value ? 'bg-primary text-white' : 'bg-surface-light text-text-muted hover:text-text'}"
			>
				<svg class="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor"><path d={ct.icon}/></svg>
				{ct.label()}
			</button>
		{/each}
	</div>
</div>

<!-- Selection list -->
<div class="flex-1 overflow-y-auto min-h-0">
	<span class="text-xs text-text-muted mb-2 block">{t('wizard.select_content')}</span>

	{#if !loaded}
		<div class="flex justify-center py-8">
			<div class="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
		</div>
	{:else if contentType === 'folder'}
		<div class="flex flex-col gap-1">
			{#each folders as f}
				<div>
					<div class="flex items-center gap-1">
						<button
							onclick={() => select(f.path, f.name)}
							class="flex-1 flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors
								{contentPath === f.path ? 'bg-primary text-white' : 'bg-surface-light text-text hover:bg-surface-lighter'}"
						>
							<svg class="w-4 h-4 flex-shrink-0 opacity-50" viewBox="0 0 24 24" fill="currentColor"><path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>
							<span class="truncate">{f.name}</span>
							<span class="text-xs opacity-60 ml-auto flex-shrink-0">{f.track_count} Titel</span>
						</button>
						{#if f.track_count > 0}
							<button onclick={() => loadTracks(f.path)} class="p-2 text-text-muted hover:text-text rounded-lg" aria-label="Titel anzeigen">
								<svg class="w-4 h-4 transition-transform {expandedFolder === f.path ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
							</button>
						{/if}
					</div>
					{#if expandedFolder === f.path && folderTracks[f.path]}
						<div class="ml-6 mt-1 flex flex-col gap-0.5">
							{#each folderTracks[f.path] as track}
								<button
									onclick={() => select(track.path, f.name + ' \u2014 ' + track.filename.replace(/\.[^.]+$/, ''))}
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

	{:else if contentType === 'stream'}
		<div class="flex flex-col gap-1">
			{#each radioStations as s}
				<button
					onclick={() => select(s.url, s.name)}
					class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors
						{contentPath === s.url ? 'bg-primary text-white' : 'bg-surface-light text-text hover:bg-surface-lighter'}"
				>
					<svg class="w-4 h-4 flex-shrink-0 opacity-50" viewBox="0 0 24 24" fill="currentColor"><path d="M3.24 6.15C2.51 6.43 2 7.17 2 8v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8c0-.83-.47-1.57-1.24-1.85L12 2 3.24 6.15zM12 16a3 3 0 1 1 0-6 3 3 0 0 1 0 6z"/></svg>
					<span class="truncate">{s.name}</span>
					{#if s.category}<span class="text-xs opacity-50 ml-auto">{capitalize(s.category)}</span>{/if}
				</button>
			{/each}
			{#if radioStations.length === 0}
				<p class="text-sm text-text-muted py-4 text-center">Keine Radiosender vorhanden</p>
			{/if}
		</div>

	{:else if contentType === 'podcast'}
		<div class="flex flex-col gap-1">
			{#each podcastList as p}
				<div>
					<div class="flex items-center gap-1">
						<button
							onclick={() => select(p.feed_url, p.name)}
							class="flex-1 flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors
								{contentPath === p.feed_url ? 'bg-primary text-white' : 'bg-surface-light text-text hover:bg-surface-lighter'}"
						>
							<svg class="w-4 h-4 flex-shrink-0 opacity-50" viewBox="0 0 24 24" fill="currentColor"><path d="M12 1a9 9 0 0 0-9 9v7a3 3 0 0 0 3 3h2v-8H5v-2a7 7 0 0 1 14 0v2h-3v8h2a3 3 0 0 0 3-3v-7a9 9 0 0 0-9-9z"/></svg>
							<span class="truncate">{p.name}</span>
							<span class="text-xs opacity-60 ml-auto flex-shrink-0">{p.episode_count} Folgen</span>
						</button>
						{#if p.episode_count > 0}
							<button onclick={() => loadEpisodes(p.id)} class="p-2 text-text-muted hover:text-text rounded-lg" aria-label="Folgen anzeigen">
								<svg class="w-4 h-4 transition-transform {expandedPodcast === p.id ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
							</button>
						{/if}
					</div>
					{#if expandedPodcast === p.id && podcastEpisodes[p.id]}
						<div class="ml-6 mt-1 flex flex-col gap-0.5 max-h-48 overflow-y-auto">
							{#each podcastEpisodes[p.id] as ep}
								<button
									onclick={() => select(ep.audio_url, p.name + ' \u2014 ' + ep.title)}
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

	{:else if contentType === 'playlist'}
		<div class="flex flex-col gap-1">
			{#each playlists as pl}
				<button
					onclick={() => select(`playlist:${pl.id}`, pl.name)}
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

	{:else if contentType === 'command'}
		<div class="flex flex-col gap-1">
			{#each commands as cmd}
				<button
					onclick={() => select(cmd.path, cmd.label())}
					class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors
						{contentPath === cmd.path ? 'bg-primary text-white' : 'bg-surface-light text-text hover:bg-surface-lighter'}"
				>
					<svg class="w-4 h-4 flex-shrink-0 opacity-50" viewBox="0 0 24 24" fill="currentColor"><path d={cmd.icon}/></svg>
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
			value={contentPath}
			oninput={(e) => select(e.currentTarget.value, name)}
			placeholder={contentType === 'stream' ? 'https://...' : 'Ordner/Datei.mp3'}
			class="w-full px-3 py-2 bg-surface-light border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary placeholder:text-text-muted/50 font-mono text-xs"
		/>
	</div>
{/if}

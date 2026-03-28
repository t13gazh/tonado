<script lang="ts">
	import { t } from '$lib/i18n';
	import { cards, library, streams, type MediaFolder, type RadioStation, type PodcastInfo } from '$lib/api';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	type Step = 'scan' | 'content' | 'done';

	let step = $state<Step>('scan');
	let scanning = $state(false);
	let scannedCardId = $state('');
	let hasExisting = $state(false);
	let error = $state('');

	// Content form
	let name = $state('');
	let contentType = $state<'folder' | 'stream' | 'podcast' | 'command'>('folder');
	let contentPath = $state('');

	// Content lists for selection
	let folders = $state<MediaFolder[]>([]);
	let radioStations = $state<RadioStation[]>([]);
	let podcastList = $state<PodcastInfo[]>([]);
	let contentListsLoaded = $state(false);

	async function loadContentLists() {
		if (contentListsLoaded) return;
		try {
			const [f, r, p] = await Promise.all([library.folders(), streams.listRadio(), streams.listPodcasts()]);
			folders = f;
			radioStations = r;
			podcastList = p;
		} catch {}
		contentListsLoaded = true;
	}

	const contentTypes = [
		{ value: 'folder' as const, label: () => t('wizard.type_folder') },
		{ value: 'stream' as const, label: () => t('wizard.type_stream') },
		{ value: 'podcast' as const, label: () => t('wizard.type_podcast') },
		{ value: 'command' as const, label: () => t('wizard.type_command') },
	];

	// Auto-start scanning on mount
	onMount(() => {
		startScan();
	});

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
					contentType = result.mapping.content_type;
					contentPath = result.mapping.content_path;
				}
				step = 'content';
				loadContentLists();
			} else {
				// Timeout — not an error, just retry
				scanning = false;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Fehler';
			scanning = false;
		}
	}

	async function saveCard() {
		if (!name.trim() || !contentPath.trim()) return;
		error = '';
		try {
			if (hasExisting) {
				await cards.update(scannedCardId, {
					name: name.trim(),
					content_type: contentType,
					content_path: contentPath.trim(),
				});
			} else {
				await cards.create({
					card_id: scannedCardId,
					name: name.trim(),
					content_type: contentType,
					content_path: contentPath.trim(),
				});
			}
			step = 'done';
		} catch (e) {
			error = e instanceof Error ? e.message : 'Fehler';
		}
	}
</script>

<div class="flex flex-col h-full p-4">
	<!-- Header -->
	<div class="flex items-center gap-3 mb-6">
		<a href="/cards" class="p-2 text-text-muted hover:text-text">
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

	<!-- Step: Scan (auto-started) -->
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
		<div class="flex-1 flex flex-col gap-4">
			{#if hasExisting}
				<div class="px-3 py-2 bg-accent/10 border border-accent/20 rounded-lg text-sm text-accent">
					{t('wizard.already_assigned')}
				</div>
			{/if}

			<!-- Content type selector -->
			<div>
				<span class="text-xs text-text-muted mb-2 block">{t('wizard.content_type')}</span>
				<div class="grid grid-cols-2 gap-2">
					{#each contentTypes as ct}
						<button
							onclick={() => (contentType = ct.value)}
							class="px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-left
								{contentType === ct.value
									? 'bg-primary text-white'
									: 'bg-surface-light text-text-muted hover:text-text'}"
						>
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

			<!-- Content selection -->
			<div class="block">
				<span class="text-xs text-text-muted mb-2 block">{t('wizard.content_path')}</span>

				{#if contentType === 'folder' && folders.length > 0}
					<div class="flex flex-col gap-1 max-h-48 overflow-y-auto mb-2">
						{#each folders as f}
							<button
								onclick={() => { contentPath = f.path; if (!name) name = f.name; }}
								class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors {contentPath === f.path ? 'bg-primary text-white' : 'bg-surface-light text-text hover:bg-surface-lighter'}"
							>
								<svg class="w-4 h-4 flex-shrink-0 opacity-50" viewBox="0 0 24 24" fill="currentColor"><path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>
								<span class="truncate">{f.name}</span>
								<span class="text-xs opacity-60 ml-auto flex-shrink-0">{f.track_count} Titel</span>
							</button>
						{/each}
					</div>
				{:else if contentType === 'stream' && radioStations.length > 0}
					<div class="flex flex-col gap-1 max-h-48 overflow-y-auto mb-2">
						{#each radioStations as s}
							<button
								onclick={() => { contentPath = s.url; if (!name) name = s.name; }}
								class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors {contentPath === s.url ? 'bg-primary text-white' : 'bg-surface-light text-text hover:bg-surface-lighter'}"
							>
								<svg class="w-4 h-4 flex-shrink-0 opacity-50" viewBox="0 0 24 24" fill="currentColor"><path d="M3.24 6.15C2.51 6.43 2 7.17 2 8v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8c0-.83-.47-1.57-1.24-1.85L12 2 3.24 6.15zM12 16a3 3 0 1 1 0-6 3 3 0 0 1 0 6z"/></svg>
								<span class="truncate">{s.name}</span>
							</button>
						{/each}
					</div>
				{:else if contentType === 'podcast' && podcastList.length > 0}
					<div class="flex flex-col gap-1 max-h-48 overflow-y-auto mb-2">
						{#each podcastList as p}
							<button
								onclick={() => { contentPath = p.feed_url; if (!name) name = p.name; }}
								class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors {contentPath === p.feed_url ? 'bg-primary text-white' : 'bg-surface-light text-text hover:bg-surface-lighter'}"
							>
								<svg class="w-4 h-4 flex-shrink-0 opacity-50" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C8.69 2 6 4.69 6 8s2.69 6 6 6 6-2.69 6-6-2.69-6-6-6zm0 10c-2.21 0-4-1.79-4-4s1.79-4 4-4 4 1.79 4 4-1.79 4-4 4zm-1.5 6.5v3h3v-3h-3z"/></svg>
								<span class="truncate">{p.name}</span>
								<span class="text-xs opacity-60 ml-auto flex-shrink-0">{p.episode_count} Folgen</span>
							</button>
						{/each}
					</div>
				{/if}

				<p class="text-[10px] text-text-muted mb-1">Oder manuell eingeben:</p>
				<input
					type="text"
					bind:value={contentPath}
					placeholder={contentType === 'stream' ? 'https://...' : 'Die drei Fragezeichen/Folge 1'}
					class="w-full px-3 py-2.5 bg-surface-light border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary placeholder:text-text-muted/50"
				/>
			</div>

			{#if error}
				<p class="text-sm text-red-400">{error}</p>
			{/if}

			<div class="mt-auto flex gap-3 pt-4">
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

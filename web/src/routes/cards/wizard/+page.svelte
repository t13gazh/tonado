<script lang="ts">
	import { t } from '$lib/i18n';
	import { cards, config } from '$lib/api';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import ContentPicker from '$lib/components/ContentPicker.svelte';

	type Step = 'scan' | 'content' | 'done';
	type ContentType = 'folder' | 'stream' | 'podcast' | 'playlist' | 'command';

	let step = $state<Step>('scan');
	let scanning = $state(false);
	let scannedCardId = $state('');
	let hasExisting = $state(false);
	let error = $state('');
	let expertMode = $state(false);

	let name = $state('');
	let contentType = $state<ContentType>('folder');
	let contentPath = $state('');

	onMount(async () => {
		try {
			const cfg = await config.getAll();
			expertMode = cfg['wizard.expert_mode'] === true;
		} catch {}
		startScan();
	});

	let waitForNewCard = $state(false);

	async function startScan() {
		scanning = true;
		error = '';
		try {
			const result = await cards.waitForScan(30, waitForNewCard);
			if (result.scanned && result.card_id) {
				scannedCardId = result.card_id;
				hasExisting = result.has_mapping ?? false;
				name = '';
				contentPath = '';
				contentType = 'folder';
				if (result.mapping) {
					name = result.mapping.name;
					contentType = result.mapping.content_type as ContentType;
					contentPath = result.mapping.content_path;
				}
				step = 'content';
			} else {
				startScan();
				return;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Fehler';
			scanning = false;
		}
	}

	function handleTypeChange(type: ContentType) {
		contentType = type;
		contentPath = '';
		name = '';
	}

	function handleSelect(path: string, autoName: string) {
		contentPath = path;
		name = autoName;
	}

	async function saveCard() {
		if (!name.trim() || !contentPath.trim()) return;
		error = '';
		try {
			const data = {
				card_id: scannedCardId,
				name: name.trim(),
				content_type: contentType as string,
				content_path: contentPath.trim(),
			};
			if (hasExisting) {
				await cards.update(scannedCardId, data);
			} else {
				await cards.create(data);
			}
			step = 'done';
		} catch (e) {
			error = e instanceof Error ? e.message : 'Fehler';
		}
	}

	function resetAndScanNext() {
		waitForNewCard = true;
		step = 'scan';
		scannedCardId = '';
		name = '';
		contentPath = '';
		contentType = 'folder';
		hasExisting = false;
		startScan();
	}
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
	<div class="flex items-center gap-2 mb-6 px-4">
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
			<p class="text-sm text-text-muted animate-pulse">{t('wizard.scanning')}</p>
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

			<ContentPicker
				{contentType}
				{contentPath}
				{name}
				{expertMode}
				onTypeChange={handleTypeChange}
				onSelect={handleSelect}
			/>

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

			{#if error}
				<p class="text-sm text-red-400">{error}</p>
			{/if}

			<div class="flex gap-3 pt-2">
				<button
					onclick={() => { waitForNewCard = true; step = 'scan'; startScan(); }}
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
					onclick={resetAndScanNext}
					class="px-8 py-2.5 bg-surface-light hover:bg-surface-lighter rounded-xl text-text text-sm font-medium transition-colors"
				>
					{t('card.add')}
				</button>
			</div>
		</div>
	{/if}
</div>
